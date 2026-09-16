"""Tests for the Prometheus instrumentation wired up by `setup_metrics`.

These pin down the label contract the Grafana dashboards in
`infra/grafana/dashboards/json/` query against. The dashboards select on
`handler` and on raw status codes (`status=~"5.."`), and compute P95 per
handler from `http_request_duration_seconds_bucket` — so the assertions below
are what stops a dependency bump from silently blanking a panel.
"""

import re

import pytest
from fastapi import APIRouter, FastAPI
from prometheus_client import CollectorRegistry
from starlette.testclient import TestClient

from app.api.middlewares.prometheus import setup_metrics

pytestmark = pytest.mark.unit


@pytest.fixture
def client() -> TestClient:
    """A minimal instrumented app: one prefixed router, one root route.

    Uses a private registry so metrics from other tests in the same process
    cannot leak into the assertions.
    """
    router = APIRouter()

    @router.get("/conversation/{conversation_id}")
    async def conversation(conversation_id: str) -> dict:
        return {"id": conversation_id}

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    setup_metrics(app, registry=CollectorRegistry())
    return TestClient(app)


def _series(client: TestClient, metric: str) -> list[str]:
    body = client.get("/metrics").text
    return [line for line in body.splitlines() if line.startswith(metric)]


def test_handler_label_keeps_the_api_version_prefix(client: TestClient) -> None:
    """The label must be the full route template, not the mount-relative path.

    On FastAPI >= 0.141 an included router's leaf `APIRoute.path` is relative
    to the mount, so a naive lookup yields `/conversation/{conversation_id}`
    and two routers mounted under different prefixes collide into one series.
    """
    client.get("/api/v1/conversation/abc-123")

    assert any(
        'handler="/api/v1/conversation/{conversation_id}"' in line for line in _series(client, "http_requests_total")
    )


def test_path_parameters_are_templated_not_recorded_verbatim(client: TestClient) -> None:
    """Two distinct ids must land on one series, or every UUID is a new one."""
    client.get("/api/v1/conversation/abc-123")
    client.get("/api/v1/conversation/def-456")

    matching = [
        line
        for line in _series(client, "http_requests_total")
        if 'handler="/api/v1/conversation/{conversation_id}"' in line
    ]
    assert len(matching) == 1
    assert matching[0].endswith(" 2.0")
    assert "abc-123" not in client.get("/metrics").text


def test_status_codes_are_recorded_ungrouped(client: TestClient) -> None:
    """Dashboards select `status=~"5.."`; grouping would erase 401 vs 404."""
    client.get("/health")

    assert any('status="200"' in line for line in _series(client, "http_requests_total"))


def test_unmatched_paths_collapse_to_a_single_series(client: TestClient) -> None:
    """A 404 scanner must not be able to mint one series per URL it probes."""
    client.get("/nope")
    client.get("/also-nope")

    lines = _series(client, "http_requests_total")
    assert any('handler="none"' in line and line.endswith(" 2.0") for line in lines)
    assert not any("nope" in line for line in lines)


def test_latency_histogram_keeps_full_bucket_resolution(client: TestClient) -> None:
    """Per-handler latency must keep prometheus_client's default 15 buckets.

    The library defaults to three (0.1/0.5/1), which would flatten the
    "P95 Latency by Endpoint" panel to uselessness.
    """
    client.get("/health")

    buckets = {
        re.search(r'le="([^"]+)"', line).group(1)
        for line in _series(client, "http_request_duration_seconds_bucket")
        if 'handler="/health"' in line
    }
    assert {"0.005", "0.25", "10.0", "+Inf"} <= buckets


def test_no_starlette_prometheus_series_remain(client: TestClient) -> None:
    """The removed package shipped `starlette_*` families nothing plotted."""
    assert "starlette_" not in client.get("/metrics").text
