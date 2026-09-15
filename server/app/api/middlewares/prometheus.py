"""Prometheus instrumentation and the /metrics endpoint.

Replaces the hand-rolled `MetricsMiddleware` and `starlette-prometheus`, both
of which recorded `http_requests_total` / `http_request_duration_seconds`
themselves. Those two names now come from here and here only — registering
them anywhere else makes `metrics.default()` swallow a `ValueError` and emit
*no* HTTP metrics at all, silently. Business metrics (`llm_*`) stay in
`app/core/metrics.py`; they do not collide.

The non-default settings below exist to keep the label contract the Grafana
dashboards in `infra/grafana/dashboards/json/` were built against — see
`tests/unit/middleware/test_metrics_setup.py`.
"""

from fastapi import FastAPI
from prometheus_client import REGISTRY, CollectorRegistry, Histogram
from prometheus_fastapi_instrumentator import Instrumentator


def setup_metrics(app: FastAPI, registry: CollectorRegistry = REGISTRY) -> None:
    """Instrument `app` and expose Prometheus metrics at /metrics.

    Args:
        app: FastAPI application instance.
        registry: Collector registry to record into. Overridden in tests so
            each case gets a clean set of series.
    """
    Instrumentator(
        # Dashboards select on `status=~"5.."`. The library's default groups
        # codes into `2xx`/`5xx`, which still satisfies that regex but would
        # make 401 vs 404 vs 429 permanently indistinguishable.
        should_group_status_codes=False,
        # Unmatched paths collapse to `handler="none"` rather than being
        # recorded verbatim, so a 404 scanner cannot mint a series per URL.
        should_group_untemplated=True,
        registry=registry,
    ).instrument(
        app,
        # The library defaults the per-handler histogram to three buckets
        # (0.1/0.5/1), which would flatten the "P95 Latency by Endpoint"
        # panel. prometheus_client's defaults span 5ms-10s, matching the
        # resolution the middleware this replaced recorded at.
        latency_lowr_buckets=Histogram.DEFAULT_BUCKETS,
    ).expose(
        app,
        # /metrics is an operational endpoint, not part of the published API.
        # Leaving it in the schema would add it to the committed openapi.json
        # and fail `make check-contract`.
        include_in_schema=False,
    )
