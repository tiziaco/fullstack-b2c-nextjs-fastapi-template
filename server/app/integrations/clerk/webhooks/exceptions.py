"""Clerk webhook exceptions."""

from app.exceptions.base import (
    AuthenticationError,
    ServiceError,
)


class WebhookError(ServiceError):
    """Base exception for webhook ingestion errors."""

    status_code = 400
    error_code = "WEBHOOK_ERROR"


class InvalidWebhookSignatureError(AuthenticationError):
    """Raised when svix verification fails, for any reason.

    Deliberately covers a forged signature, a missing svix header, and a
    timestamp outside the tolerance window alike. Distinguishing them in the
    response would tell an attacker which check they failed.
    """

    error_code = "WEBHOOK_INVALID_SIGNATURE"


class WebhookPayloadTooLargeError(WebhookError):
    """Raised when the request body exceeds the accepted size."""

    status_code = 413
    error_code = "WEBHOOK_PAYLOAD_TOO_LARGE"
