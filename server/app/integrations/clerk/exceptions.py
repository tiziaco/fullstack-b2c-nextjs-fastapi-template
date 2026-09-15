"""Clerk service exceptions."""

from app.exceptions.base import (
    NotFoundError,
    ServiceError,
)


class ClerkServiceError(ServiceError):
    """Base exception for Clerk service errors."""

    status_code = 502
    error_code = "CLERK_SERVICE_ERROR"


class ClerkUserNotFoundError(NotFoundError):
    """Raised when a user is not found in Clerk."""

    error_code = "CLERK_USER_NOT_FOUND"


class ClerkAPIError(ClerkServiceError):
    """Raised when Clerk API returns an error."""

    error_code = "CLERK_API_ERROR"


class ClerkRateLimitError(ClerkServiceError):
    """Raised when Clerk API rate limit is exceeded."""

    status_code = 429
    error_code = "CLERK_RATE_LIMIT"


class ClerkAuthenticationError(ClerkServiceError):
    """Raised when Clerk API authentication fails."""

    status_code = 401
    error_code = "CLERK_AUTH_ERROR"
