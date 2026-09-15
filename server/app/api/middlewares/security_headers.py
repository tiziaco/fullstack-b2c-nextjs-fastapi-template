"""Security headers middleware for FastAPI application."""

from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.config import Environment, settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware that adds HTTP security headers to every response.

    Adds standard protective headers to prevent common web vulnerabilities
    such as MIME-type sniffing, clickjacking, and XSS attacks.
    In production, also adds Strict-Transport-Security (HSTS).
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add security headers to the response.

        Args:
            request: The incoming request
            call_next: The next middleware or route handler

        Returns:
            Response: The response with security headers added
        """
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.ENVIRONMENT == Environment.PRODUCTION:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
