"""Structured HTTP access logging middleware for request/response tracking."""

import time
from typing import TypedDict

import structlog
from asgi_correlation_id import correlation_id
from starlette.types import (
    ASGIApp,
    Receive,
    Scope,
    Send,
)
from uvicorn.protocols.utils import get_path_with_query_string


class AccessInfo(TypedDict, total=False):
    """Type for storing access log information."""

    status_code: int
    start_time: float


class AccessLogMiddleware:
    """Middleware to log HTTP access information in structured format.

    This middleware:
    - Captures HTTP request/response details (method, path, status, duration)
    - Binds correlation_id to access logs
    - Excludes health check endpoints from logging
    - Logs in structured format compatible with the app's structlog configuration
    """

    def __init__(
        self,
        app: ASGIApp,
        exclude_paths: tuple[str, ...] = ("/health", "/ready", "/metrics", "/readiness"),
    ):
        """Initialize the access log middleware.

        Args:
            app: The ASGI application
            exclude_paths: Tuple of paths to exclude from access logging
        """
        self.app = app
        self.exclude_paths = exclude_paths
        # Get a structlog logger and bind component context
        self.access_logger = structlog.get_logger().bind(component="api-access")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process HTTP requests and log access information.

        Args:
            scope: ASGI scope dictionary
            receive: ASGI receive callable
            send: ASGI send callable
        """
        # Only process HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Check if path should be excluded from logging
        path = scope["path"]
        if path in self.exclude_paths:
            await self.app(scope, receive, send)
            return

        info = AccessInfo()

        # Inner send function to capture response details
        async def inner_send(message):
            if message["type"] == "http.response.start":
                info["status_code"] = message["status"]
            await send(message)

        # Start timing
        info["start_time"] = time.perf_counter_ns()

        try:
            await self.app(scope, receive, inner_send)
        finally:
            # Calculate request duration
            duration_ns = time.perf_counter_ns() - info["start_time"]
            duration_ms = round(duration_ns / 1_000_000, 2)  # Convert to milliseconds

            # Extract request details
            client_host, client_port = scope.get("client", ("unknown", 0))
            http_method = scope["method"]
            http_version = scope.get("http_version", "1.1")
            url = get_path_with_query_string(scope)
            status_code = info.get("status_code", 500)

            # Extract user_agent from headers
            user_agent = "unknown"
            for header_name, header_value in scope.get("headers", []):
                if header_name.lower() == b"user-agent":
                    user_agent = header_value.decode("utf-8", errors="replace")
                    break

            # Get user_id from request.state if available (set by AuthMiddleware)
            # Note: We can't access request.state directly from ASGI middleware,
            # so user_id will be bound in LoggingContextMiddleware instead
            # and will automatically appear in these logs via context propagation

            # Log access information with custom format: METHOD STATUS "{path}" HTTP/version
            self.access_logger.info(
                f'{client_host}:{client_port} - {http_method} {status_code} "{path}" HTTP/{http_version}',
                http={
                    "url": str(url),
                    "status_code": status_code,
                    "method": http_method,
                    "request_id": correlation_id.get(),
                    "version": http_version,
                    "user_agent": user_agent,
                },
                network={
                    "client": {
                        "ip": client_host,
                        "port": client_port,
                    }
                },
                duration_ms=duration_ms,
            )
