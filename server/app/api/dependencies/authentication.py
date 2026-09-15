"""Authentication dependencies — identity resolution only.

Resource and role-based authorization guards live in `authorization.py`.
"""

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import OAuth2AuthorizationCodeBearer

from app.api.dependencies.database import DbSession
from app.core.config import settings
from app.core.logging import bind_context, logger
from app.exceptions.base import AuthenticationError, AuthorizationError
from app.models.enums import Role
from app.models.user import User
from app.services.user import user_service

oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl=settings.auth.AUTHORIZE_URL,
    tokenUrl=settings.auth.TOKEN_URL,
    scopes={
        "openid": "OpenID Connect",
        "profile": "Profile information",
        "email": "Email address",
        "offline_access": "Refresh token",
    },
    auto_error=False,
)


def get_clerk_id(request: Request) -> str:
    """Extract clerk_id from request.state (set by AuthMiddleware)."""
    clerk_id = getattr(request.state, "clerk_id", None)
    if not clerk_id:
        logger.error("clerk_id_not_in_request_state")
        raise AuthenticationError("Authentication required")
    return clerk_id


async def get_current_user(
    request: Request,
    session: DbSession,
    clerk_id: str = Depends(get_clerk_id),
    _token: str = Depends(oauth2_scheme),
) -> User:
    """Get the current authenticated user with JIT provisioning."""
    try:
        user = await user_service.resolve_user(clerk_id, session)
        request.state.user_id = user.id
        bind_context(user_id=user.id)
    except Exception as e:
        logger.error("user_provisioning_failed", clerk_id=clerk_id, error=str(e))
        raise AuthenticationError("Failed to provision user") from e
    return user


async def get_current_role(
    request: Request,
    _token: str = Depends(oauth2_scheme),
) -> Role:
    """Extract the platform role from request.state.

    This is the backend portability seam. The role arrives as a custom `role`
    claim on the Clerk session token, sourced from publicMetadata.role. The
    token is the only source — there is deliberately no database mirror and no
    provider-API fallback, so a role change propagates on the next token
    refresh and nothing can go stale independently.

    Raises:
        AuthorizationError: If no role is present or the role is unrecognised.
    """
    raw = getattr(request.state, "role", None)

    if not raw:
        raise AuthorizationError("No role in token")

    try:
        return Role(raw)
    except ValueError:
        raise AuthorizationError(f"Unknown role: {raw}")


# ---------------------------------------------------------------------------
# Identity type aliases
# ---------------------------------------------------------------------------

CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentRole = Annotated[Role, Depends(get_current_role)]
