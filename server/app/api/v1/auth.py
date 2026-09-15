"""User profile endpoints for the API.

This module provides endpoints for retrieving and managing the authenticated user's profile.
Authentication is handled by Clerk - there are no register/login endpoints.
"""

from fastapi import (
    APIRouter,
    Request,
)

from app.api.dependencies.authentication import CurrentUser
from app.api.dependencies.database import DbSession
from app.core.config import settings
from app.core.limiter import limiter
from app.schemas.auth import UserResponse
from app.services.user import user_service

router = APIRouter()


@router.get(
    "/me",
    operation_id="getMe",
    response_model=UserResponse,
    summary="Get current user profile",
    description="Retrieve the authenticated user's profile information. "
    "Creates the user in the database on first access (JIT provisioning).",
)
async def get_me(user: CurrentUser):
    """Get the current authenticated user's profile.

    Args:
        user: The authenticated user (resolved via JIT provisioning).

    Returns:
        UserResponse: The user's profile information.
    """
    return UserResponse.model_validate(user)


@router.delete(
    "/me",
    operation_id="deleteMe",
    status_code=204,
    summary="Delete current user account (GDPR)",
    description="Permanently delete the authenticated user's account and all associated data. "
    "This action cannot be undone.",
)
@limiter.limit(settings.rate_limits.endpoints.CHAT[0])
async def delete_me(
    request: Request,
    user: CurrentUser,
    db_session: DbSession,
):
    """Delete the current user's account in a GDPR-compliant manner.

    Steps performed:
    1. Delete user from Clerk (invalidates all future JWTs)
    2. Soft-delete all conversation records + collect their IDs
    3. Clear LangGraph checkpoint data for each conversation (message PII)
    4. Delete mem0 long-term memory (extracted fact PII)
    5. Anonymize the user record in DB

    Args:
        request: The FastAPI request object for rate limiting.
        user: The authenticated user.
        db_session: Database session.
    """
    original_clerk_id = user.clerk_id  # captured before erase_user anonymises it

    # Delete from Clerk first so the JWT cannot re-provision the account.
    # The webhook path skips this step — there, Clerk's deletion is the trigger.
    await user_service.delete_user_from_clerk(original_clerk_id)

    await user_service.erase_user(user, db_session)
