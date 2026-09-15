"""Adversarial tests for Clerk webhook signature verification.

This dependency is the entire security boundary for the webhook endpoint —
no JWT, no session, nothing else authenticates the caller. Every test here
is an attack the endpoint must reject.
"""

import json
from datetime import (
    UTC,
    datetime,
    timedelta,
)

import pytest
from fastapi import Request
from pydantic import SecretStr
from svix.webhooks import Webhook

from app.core.config import settings
from app.integrations.clerk.webhooks.exceptions import (
    InvalidWebhookSignatureError,
    WebhookPayloadTooLargeError,
)
from app.integrations.clerk.webhooks.verification import (
    MAX_WEBHOOK_BODY_BYTES,
    verify_clerk_webhook,
)

pytestmark = pytest.mark.unit

TEST_SECRET = "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw"
OTHER_SECRET = "whsec_TG9yZW1JcHN1bURvbG9yU2l0QW1ldENvbnM="

PAYLOAD = {
    "type": "user.created",
    "object": "event",
    "timestamp": 1654012591835,
    "instance_id": "ins_123",
    "data": {"id": "user_abc", "updated_at": 1654012591835},
}


def signed_headers(body: str, secret: str = TEST_SECRET, msg_id: str = "msg_1", ts=None) -> dict:
    ts = ts or datetime.now(tz=UTC)
    return {
        "svix-id": msg_id,
        "svix-timestamp": str(int(ts.timestamp())),
        "svix-signature": Webhook(secret).sign(msg_id, ts, body),
    }


def make_request(body: bytes, headers: dict) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/webhooks/clerk",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


def make_streaming_request(chunk: bytes, chunk_count: int, headers: dict) -> tuple[Request, dict]:
    """Build a request whose body arrives in chunks, counting what is consumed.

    The returned dict is live: `delivered` is the number of body bytes the
    dependency has actually pulled off the wire so far. It is how a test tells
    "rejected after reading a bounded prefix" from "rejected after buffering
    the whole thing", which a 413 assertion alone cannot distinguish.
    """
    consumed = {"delivered": 0, "chunks": 0}
    remaining = chunk_count

    async def receive():
        nonlocal remaining
        if remaining <= 0:
            return {"type": "http.request", "body": b"", "more_body": False}
        remaining -= 1
        consumed["delivered"] += len(chunk)
        consumed["chunks"] += 1
        return {"type": "http.request", "body": chunk, "more_body": remaining > 0}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/webhooks/clerk",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }

    return Request(scope, receive), consumed


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(settings.auth, "WEBHOOK_SIGNING_SECRET", SecretStr(TEST_SECRET))


async def test_valid_signature_returns_parsed_event():
    body = json.dumps(PAYLOAD)
    verified = await verify_clerk_webhook(make_request(body.encode(), signed_headers(body)))

    assert verified.event.type == "user.created"
    assert verified.event.data["id"] == "user_abc"
    assert verified.event.timestamp == 1654012591835
    assert verified.event.instance_id == "ins_123"
    # The svix message id is the dedup key a future dedup table would use,
    # and the value the dispatch log line is matched against in Clerk's
    # dashboard. It is carried off the header, not out of the payload.
    assert verified.message_id == "msg_1"


async def test_tampered_body_is_rejected():
    body = json.dumps(PAYLOAD)
    headers = signed_headers(body)
    tampered = json.dumps({**PAYLOAD, "data": {"id": "user_attacker"}})

    with pytest.raises(InvalidWebhookSignatureError):
        await verify_clerk_webhook(make_request(tampered.encode(), headers))


async def test_reserialised_body_is_rejected():
    """Proves we verify raw bytes. Re-serialising reorders keys and breaks the HMAC."""
    body = json.dumps(PAYLOAD)
    headers = signed_headers(body)
    reserialised = json.dumps(json.loads(body), sort_keys=True, separators=(", ", ": "))

    assert reserialised != body
    with pytest.raises(InvalidWebhookSignatureError):
        await verify_clerk_webhook(make_request(reserialised.encode(), headers))


async def test_signature_from_a_different_secret_is_rejected():
    body = json.dumps(PAYLOAD)
    headers = signed_headers(body, secret=OTHER_SECRET)

    with pytest.raises(InvalidWebhookSignatureError):
        await verify_clerk_webhook(make_request(body.encode(), headers))


async def test_stale_timestamp_is_rejected():
    """svix enforces a five-minute tolerance; this is the replay window bound."""
    body = json.dumps(PAYLOAD)
    old = datetime.now(tz=UTC) - timedelta(minutes=10)

    with pytest.raises(InvalidWebhookSignatureError):
        await verify_clerk_webhook(make_request(body.encode(), signed_headers(body, ts=old)))


async def test_future_timestamp_is_rejected():
    body = json.dumps(PAYLOAD)
    future = datetime.now(tz=UTC) + timedelta(minutes=10)

    with pytest.raises(InvalidWebhookSignatureError):
        await verify_clerk_webhook(make_request(body.encode(), signed_headers(body, ts=future)))


async def test_signature_bound_to_a_different_message_id_is_rejected():
    """The msg id is part of the signed artifact, so headers cannot be mixed."""
    body = json.dumps(PAYLOAD)
    headers = signed_headers(body, msg_id="msg_1")
    headers["svix-id"] = "msg_2"

    with pytest.raises(InvalidWebhookSignatureError):
        await verify_clerk_webhook(make_request(body.encode(), headers))


@pytest.mark.parametrize("missing", ["svix-id", "svix-timestamp", "svix-signature"])
async def test_missing_svix_header_is_rejected(missing):
    body = json.dumps(PAYLOAD)
    headers = signed_headers(body)
    del headers[missing]

    with pytest.raises(InvalidWebhookSignatureError):
        await verify_clerk_webhook(make_request(body.encode(), headers))


async def test_no_headers_at_all_is_rejected():
    body = json.dumps(PAYLOAD)
    with pytest.raises(InvalidWebhookSignatureError):
        await verify_clerk_webhook(make_request(body.encode(), {}))


async def test_garbage_signature_header_is_rejected():
    """A structurally invalid signature must not escape as a 500."""
    body = json.dumps(PAYLOAD)
    headers = signed_headers(body)
    headers["svix-signature"] = "not-a-signature"

    with pytest.raises(InvalidWebhookSignatureError):
        await verify_clerk_webhook(make_request(body.encode(), headers))


async def test_non_numeric_timestamp_header_is_rejected():
    body = json.dumps(PAYLOAD)
    headers = signed_headers(body)
    headers["svix-timestamp"] = "tomorrow"

    with pytest.raises(InvalidWebhookSignatureError):
        await verify_clerk_webhook(make_request(body.encode(), headers))


async def test_correctly_signed_non_json_body_is_rejected():
    """A valid HMAC does not make a body parseable; it must not escape as a 500."""
    body = "not json at all"

    with pytest.raises(InvalidWebhookSignatureError):
        await verify_clerk_webhook(make_request(body.encode(), signed_headers(body)))


async def test_correctly_signed_body_missing_required_fields_is_rejected():
    """Envelope validation failures collapse into the same opaque rejection."""
    body = json.dumps({"object": "event", "data": {"id": "user_abc"}})

    with pytest.raises(InvalidWebhookSignatureError):
        await verify_clerk_webhook(make_request(body.encode(), signed_headers(body)))


async def test_oversized_body_is_rejected_before_verification():
    """The size check must precede the HMAC so abuse costs us nothing."""
    body = b"x" * (MAX_WEBHOOK_BODY_BYTES + 1)

    with pytest.raises(WebhookPayloadTooLargeError):
        await verify_clerk_webhook(make_request(body, {}))


async def test_oversized_body_never_reaches_the_hmac(monkeypatch):
    """Explicit proof of ordering: the signer is never constructed."""

    def _explode(*args, **kwargs):
        raise AssertionError("HMAC verification ran on an oversized body")

    monkeypatch.setattr("app.integrations.clerk.webhooks.verification.Webhook", _explode)
    body = b"x" * (MAX_WEBHOOK_BODY_BYTES + 1)

    with pytest.raises(WebhookPayloadTooLargeError):
        await verify_clerk_webhook(make_request(body, signed_headers("{}")))


async def test_oversized_body_is_abandoned_mid_stream():
    """The cap must bound what we allocate, not merely what we hash.

    `request.body()` buffers the entire body before its length can be checked,
    so a size check after it bounds the HMAC and nothing else. This asserts the
    stronger property: a nominally 256 MiB body is dropped after a bounded
    prefix. A 413 assertion alone would pass even if we had buffered all of it.
    """
    chunk = b"x" * (64 * 1024)
    nominal_size = 4096 * len(chunk)
    request, consumed = make_streaming_request(chunk, 4096, {})

    assert nominal_size > 100 * MAX_WEBHOOK_BODY_BYTES, "the body must dwarf the cap"

    with pytest.raises(WebhookPayloadTooLargeError) as exc_info:
        await verify_clerk_webhook(request)

    # Peak allocation is the cap plus the one in-flight chunk that crossed it.
    assert consumed["delivered"] <= MAX_WEBHOOK_BODY_BYTES + len(chunk)
    assert consumed["delivered"] < nominal_size
    assert exc_info.value.context == {"size": consumed["delivered"]}


async def test_a_body_arriving_in_chunks_is_reassembled_and_verified():
    """Streaming must not corrupt the signed artifact: chunk joins are exact."""
    body = json.dumps(PAYLOAD).encode()
    chunks = [body[i : i + 7] for i in range(0, len(body), 7)]
    assert len(chunks) > 1

    consumed = {"n": 0}

    async def receive():
        if consumed["n"] >= len(chunks):
            return {"type": "http.request", "body": b"", "more_body": False}
        chunk = chunks[consumed["n"]]
        consumed["n"] += 1
        return {"type": "http.request", "body": chunk, "more_body": consumed["n"] < len(chunks)}

    headers = signed_headers(body.decode())
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/webhooks/clerk",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }

    verified = await verify_clerk_webhook(Request(scope, receive))

    assert verified.event.type == "user.created"
    assert verified.event.data["id"] == "user_abc"


async def test_an_oversized_chunked_body_declaring_no_length_is_rejected():
    """A Content-Length check alone would be theatre: an attacker omits it."""
    chunk = b"x" * (32 * 1024)
    request, consumed = make_streaming_request(chunk, 512, {"transfer-encoding": "chunked"})

    with pytest.raises(WebhookPayloadTooLargeError):
        await verify_clerk_webhook(request)

    assert consumed["delivered"] <= MAX_WEBHOOK_BODY_BYTES + len(chunk)


async def test_body_at_the_size_limit_still_reaches_verification():
    """The cap is exclusive: a body of exactly MAX bytes is verified, not refused."""
    body = b"x" * MAX_WEBHOOK_BODY_BYTES

    with pytest.raises(InvalidWebhookSignatureError):
        await verify_clerk_webhook(make_request(body, {}))


async def test_every_rejection_is_indistinguishable_to_the_caller():
    """No response field may tell an attacker which check they failed.

    The centralized handler renders `message` and `context` into the response
    body, so any variation between failure modes leaks the reason.
    """
    body = json.dumps(PAYLOAD)
    stale = datetime.now(tz=UTC) - timedelta(minutes=10)
    no_signature = signed_headers(body)
    del no_signature["svix-signature"]

    attacks = [
        make_request(body.encode(), {}),
        make_request(body.encode(), no_signature),
        make_request(body.encode(), signed_headers(body, secret=OTHER_SECRET)),
        make_request(b'{"type": "user.deleted", "data": {}}', signed_headers(body)),
        make_request(body.encode(), signed_headers(body, ts=stale)),
        make_request(b"not json", signed_headers("not json")),
    ]

    seen = set()
    for request in attacks:
        with pytest.raises(InvalidWebhookSignatureError) as exc_info:
            await verify_clerk_webhook(request)
        exc = exc_info.value
        assert exc.context == {}, "exception context is rendered into the response body"
        seen.add((exc.status_code, exc.error_code, exc.message))

    assert len(seen) == 1, f"failure modes are distinguishable: {seen}"
    assert seen == {(401, "WEBHOOK_INVALID_SIGNATURE", "Invalid webhook signature")}


@pytest.mark.parametrize("bad_secret", ["", "whsec_", "not-base64!!"])
async def test_an_unusable_signing_secret_fails_closed(monkeypatch, bad_secret):
    """A misconfigured deployment must never accept unverified events.

    REQUIRED_ENV_VARS in scripts/docker-entrypoint.sh stops a container
    without the secret from starting, so this is defence in depth: whatever
    an unusable secret does, it must never be "trust the caller". An empty
    secret surfaces as a 500 rather than a 401 on purpose — the caller is not
    at fault and the failure should be loud for operators.
    """
    monkeypatch.setattr(settings.auth, "WEBHOOK_SIGNING_SECRET", SecretStr(bad_secret))
    body = json.dumps(PAYLOAD)

    with pytest.raises(Exception) as exc_info:
        await verify_clerk_webhook(make_request(body.encode(), signed_headers(body)))

    # pytest.raises already proves no event was returned; these prove the
    # failure tells the caller nothing about the secret it was configured with.
    assert bad_secret not in str(exc_info.value) or not bad_secret
    assert getattr(exc_info.value, "context", {}) == {}
