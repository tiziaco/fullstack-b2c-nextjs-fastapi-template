"""Clerk integration — the outbound Backend API client and its errors.

Inbound traffic (webhooks Clerk pushes to us) lives in the `webhooks`
subpackage, which is deliberately not re-exported here: the two directions
have opposite dependency shapes and only the route imports the inbound half.
"""

from app.integrations.clerk.client import (
    ClerkClient,
    clerk_client,
)
from app.integrations.clerk.exceptions import (
    ClerkAPIError,
    ClerkAuthenticationError,
    ClerkRateLimitError,
    ClerkServiceError,
    ClerkUserNotFoundError,
)

__all__ = [
    "ClerkAPIError",
    "ClerkAuthenticationError",
    "ClerkClient",
    "ClerkRateLimitError",
    "ClerkServiceError",
    "ClerkUserNotFoundError",
    "clerk_client",
]
