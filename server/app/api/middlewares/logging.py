"""Custom middleware for binding authentication context to structured logging."""

from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.logging import (
    bind_context,
    clear_context,
)


class LoggingContextMiddleware(BaseHTTPMiddleware):
    """Middleware for binding user_id to logging context.

    This middleware reads authentication context from request.state (populated by AuthMiddleware)
    and binds it to the structured logging context for all subsequent logs in the request.
    Note: conversation_id is passed as path parameter in endpoints, not via auth token.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Bind authentication context to logging from request.state.

        Args:
            request: The incoming request
            call_next: The next middleware or route handler

        Returns:
            Response: The response from the application
        """
        try:
            # Clear any existing context from previous requests
            clear_context()

            # Initially bind clerk_id if available (before user provisioning)
            # This will be updated with the internal UUID after user provisioning
            if hasattr(request.state, "clerk_id") and request.state.clerk_id:
                bind_context(clerk_id=request.state.clerk_id)

            # Process the request
            response = await call_next(request)

            return response

        finally:
            # Always clear context after request is complete to avoid leaking to other requests
            clear_context()
