"""Prometheus metrics configuration for the application.

Business metrics only. The HTTP request families (`http_requests_total`,
`http_request_duration_seconds`) are recorded by the instrumentator wired up
in `app/api/middlewares/prometheus.py` — redefining them here would collide
and silently disable *all* HTTP metrics.
"""

from prometheus_client import (
    Counter,
    Histogram,
)

# Custom business metrics
orders_processed = Counter("orders_processed_total", "Total number of orders processed")

llm_inference_duration_seconds = Histogram(
    "llm_inference_duration_seconds",
    "Time spent processing LLM inference",
    ["model"],
    buckets=[0.1, 0.3, 0.5, 1.0, 2.0, 5.0],
)


llm_stream_duration_seconds = Histogram(
    "llm_stream_duration_seconds",
    "Time spent processing LLM stream inference",
    ["model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
)


tool_calls_total = Counter(
    "tool_calls_total",
    "Agent tool invocations by tool and outcome",
    ["tool", "outcome"],
)

tool_call_duration_seconds = Histogram(
    "tool_call_duration_seconds",
    "Time spent executing an agent tool",
    ["tool"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
)


# `app_`-prefixed on purpose. A collision with a name the instrumentator
# registers would make `metrics.default()` swallow a ValueError and emit no
# HTTP metrics at all (see the module docstring), and `exceptions_total` is a
# plausible name for a library to take.
#
# `error_code` is a ServiceError class attribute from a closed set and
# `exception_type` is bounded by which classes actually escape, so neither
# label is caller-controlled.
#
# Not counted: exceptions raised mid-stream. Once an SSE response has begun,
# nothing propagates back to an exception handler, and the chat stream
# endpoint is exactly that case.
app_exceptions_total = Counter(
    "app_exceptions_total",
    "Exceptions surfaced to clients, by error code and exception class",
    ["error_code", "exception_type"],
)
