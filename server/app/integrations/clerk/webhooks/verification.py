"""Clerk webhook signature verification.

This is the only thing authenticating the webhook endpoint — there is no
JWT and no session. AuthMiddleware runs permissively and sets no identity
for these requests, by design: the svix signature is the credential.
"""

import json
from typing import Final

from fastapi import Request
from svix.webhooks import Webhook
from svix.webhooks import WebhookVerificationError as SvixWebhookVerificationError

from app.core.config import settings
from app.core.logging import logger
from app.integrations.clerk.webhooks.exceptions import (
    InvalidWebhookSignatureError,
    WebhookPayloadTooLargeError,
)
from app.integrations.clerk.webhooks.schemas import (
    ClerkEvent,
    VerifiedEvent,
)

# Clerk payloads are a few KB. Nothing upstream bounds the request body — no
# ASGI-server flag or reverse-proxy setting caps it here, no middleware
# limits it, and this route is deliberately unauthenticated and unthrottled
# — so the cap has to be enforced here, and enforced while reading rather
# than after. See _read_body_capped.
MAX_WEBHOOK_BODY_BYTES: Final[int] = 256 * 1024


async def _read_body_capped(request: Request) -> bytes:
    """Read the request body, abandoning it as soon as it exceeds the cap.

    `request.body()` would buffer the whole body first and only then let us
    measure it, which bounds what we hash but not what we allocate. Consuming
    `request.stream()` instead lets us stop at the first chunk that crosses the
    cap, so peak allocation is the cap plus the single in-flight chunk no
    matter how much the caller sends. A Content-Length pre-check is not enough
    on its own: an attacker using chunked transfer-encoding simply omits the
    header, and this endpoint's threat model is a deliberate attacker.

    Args:
        request: The incoming request. Its stream is consumed exactly once, so
            `request.body()` must not be awaited afterwards.

    Returns:
        The raw request body.

    Raises:
        WebhookPayloadTooLargeError: More than MAX_WEBHOOK_BODY_BYTES arrived.
    """
    buffer = bytearray()
    received = 0

    async for chunk in request.stream():
        received += len(chunk)
        if received > MAX_WEBHOOK_BODY_BYTES:
            # Bail before appending, so the oversized chunk is never retained
            # and the remaining chunks are never requested.
            logger.warning("webhook_payload_too_large", size=received)
            raise WebhookPayloadTooLargeError("Webhook payload too large", size=received)
        buffer.extend(chunk)

    return bytes(buffer)


async def verify_clerk_webhook(request: Request) -> VerifiedEvent:
    """Verify a Clerk webhook signature and return the parsed event.

    Args:
        request: The incoming request. Its raw body is read exactly once.

    Returns:
        The verified event, paired with svix's message id.

    Raises:
        WebhookPayloadTooLargeError: Body exceeds MAX_WEBHOOK_BODY_BYTES.
        InvalidWebhookSignatureError: Signature invalid, headers missing,
            timestamp outside svix's five-minute tolerance, or the verified
            body is not a Clerk event envelope.
    """
    body = await _read_body_capped(request)

    # Starlette lower-cases header names, so "svix-id" matches whatever
    # casing arrived on the wire.
    headers = dict(request.headers)
    secret = settings.auth.WEBHOOK_SIGNING_SECRET.get_secret_value()

    try:
        # The raw bytes are the signed artifact. Parsing and re-serialising
        # would change key order or whitespace and break the HMAC. svix
        # verifies without deserialising and returns None, so the envelope is
        # decoded here — from the same `body` object the HMAC just accepted.
        Webhook(secret).verify(body, headers)
        event = ClerkEvent.model_validate(json.loads(body))
    except (SvixWebhookVerificationError, ValueError) as exc:
        # One error for every failure mode: bad signature, missing header,
        # stale timestamp, malformed secret, unparseable body. Never reveal
        # which — the handler renders message and context to the caller.
        logger.warning("webhook_verification_failed", reason=type(exc).__name__)
        raise InvalidWebhookSignatureError("Invalid webhook signature") from exc

    # svix rejects a delivery with no svix-id before we get here, so the
    # header is present by the time verification has passed. Defaulting to ""
    # rather than indexing keeps a malformed-but-somehow-signed request from
    # raising KeyError past the security boundary.
    message_id = headers.get("svix-id", "")

    logger.debug("webhook_verified", event_type=event.type, message_id=message_id)
    return VerifiedEvent(event=event, message_id=message_id)
