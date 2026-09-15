"""Authentication middleware for Clerk JWT token extraction and verification."""

from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.logging import logger
from app.utils.auth import clerk_jwt_verifier


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware for extracting and verifying Clerk JWT tokens.

    Stores the following in request.state after a valid token:
      - clerk_id : Clerk user ID (sub claim)
      - role     : platform role, from the custom `role` claim, or None

    The `role` claim is configured in the Clerk dashboard as a session token
    customization sourcing user.public_metadata.role. There is no organization
    context in this template.

    The middleware is permissive — it does not block requests with invalid/missing
    tokens. Route-level dependencies determine if authentication is required.

    Note: after user provisioning, request.state.user_id is set to the internal UUID.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Parse the Clerk token, if any, and stash the identity on request.state."""
        request.state.clerk_id = None
        request.state.user_id = None
        request.state.role = None

        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                token = auth_header.split(" ")[1]
                payload = clerk_jwt_verifier.verify_token(token)

                if payload:
                    request.state.clerk_id = payload.get("sub")
                    request.state.role = payload.get("role")

                    logger.debug(
                        "token_verified_in_middleware",
                        clerk_id=request.state.clerk_id,
                        role=request.state.role,
                        path=request.url.path,
                    )
                else:
                    logger.debug("token_verification_failed_in_middleware", path=request.url.path)

            except (IndexError, ValueError) as e:
                logger.debug("token_extraction_failed", error=str(e), path=request.url.path)
        elif request.url.path not in ("/health", "/metrics"):
            logger.debug("no_auth_header_present", path=request.url.path)

        return await call_next(request)
