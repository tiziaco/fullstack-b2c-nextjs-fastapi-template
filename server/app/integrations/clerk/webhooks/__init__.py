"""Clerk webhook ingestion — verify, parse, dispatch.

The whole inbound path reads in order from this package: `verification`
authenticates the request and decodes the envelope, `schemas` defines what it
produces, `dispatcher` routes it, and `handlers/` translates each event into
domain calls.
"""

from app.integrations.clerk.webhooks.dispatcher import clerk_dispatcher
from app.integrations.clerk.webhooks.exceptions import (
    InvalidWebhookSignatureError,
    WebhookError,
    WebhookPayloadTooLargeError,
)
from app.integrations.clerk.webhooks.schemas import (
    ClerkEvent,
    VerifiedEvent,
    WebhookContext,
)
from app.integrations.clerk.webhooks.verification import verify_clerk_webhook

__all__ = [
    "ClerkEvent",
    "VerifiedEvent",
    "WebhookContext",
    "InvalidWebhookSignatureError",
    "WebhookError",
    "WebhookPayloadTooLargeError",
    "clerk_dispatcher",
    "verify_clerk_webhook",
]
