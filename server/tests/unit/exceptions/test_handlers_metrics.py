"""Tests for the `app_exceptions_total` counter recorded by the exception handlers.

`http_requests_total` records the status code, which is not enough to identify a
failure: every exception in `app/services/llm/exceptions.py` carries 503, so
five distinct causes share one series. These pin the labels that tell them
apart.
"""

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from prometheus_client import REGISTRY
from starlette.testclient import TestClient

from app.exceptions.base import ServiceError
from app.exceptions.handlers import (
    global_exception_handler,
    service_exception_handler,
    validation_exception_handler,
)
from app.services.llm.exceptions import LLMRateLimitError

pytestmark = pytest.mark.unit

METRIC = "app_exceptions_total"


@pytest.fixture
def client() -> TestClient:
    """An app wired with the real handlers, raising from real routes.

    `raise_server_exceptions=False` so the unhandled case is served by
    `global_exception_handler` instead of propagating into the test.
    """
    app = FastAPI()

    @app.get("/service-error")
    async def service_error() -> None:
        raise LLMRateLimitError("upstream said no")

    @app.get("/unhandled")
    async def unhandled() -> None:
        raise RuntimeError("something nobody anticipated")

    @app.get("/needs-a-number")
    async def needs_a_number(count: int) -> dict:
        return {"count": count}

    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ServiceError, service_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)
    return TestClient(app, raise_server_exceptions=False)


def _count(error_code: str, exception_type: str) -> float:
    """Current value of one labelled series, 0 before it has been touched.

    `app/core/metrics.py` registers on the default registry at import, so these
    accumulate for the whole session and only deltas are meaningful.
    """
    value = REGISTRY.get_sample_value(METRIC, {"error_code": error_code, "exception_type": exception_type})
    return value or 0.0


def _total() -> float:
    """Sum across every label combination currently registered."""
    return sum(
        sample.value
        for metric in REGISTRY.collect()
        if metric.name == "app_exceptions"
        for sample in metric.samples
        if sample.name == METRIC
    )


class TestExceptionCounter:
    """The labels that survive into Prometheus."""

    def test_service_error_is_counted_by_error_code(self, client: TestClient) -> None:
        """The error_code, not the status code, is what distinguishes the cause."""
        before = _count("LLM_RATE_LIMIT", "LLMRateLimitError")

        response = client.get("/service-error")

        assert response.status_code == 503
        assert _count("LLM_RATE_LIMIT", "LLMRateLimitError") == before + 1

    def test_unhandled_exception_is_counted_as_unhandled(self, client: TestClient) -> None:
        """A generic 500 hides the cause from the client; the label keeps it."""
        before = _count("UNHANDLED", "RuntimeError")

        response = client.get("/unhandled")

        assert response.status_code == 500
        assert _count("UNHANDLED", "RuntimeError") == before + 1

    def test_validation_errors_are_not_counted(self, client: TestClient) -> None:
        """422s are already legible in http_requests_total.

        This counter is for failures whose cause the status code hides, so
        instrumenting the validation handler would add noise, not information.
        """
        before = _total()

        response = client.get("/needs-a-number?count=not-a-number")

        assert response.status_code == 422
        assert _total() == before
