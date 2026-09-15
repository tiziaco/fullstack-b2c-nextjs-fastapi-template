"""End-to-end webhook route tests against a real database."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, Response
from sqlmodel import select
from svix.webhooks import Webhook

from app.integrations.clerk.webhooks.dispatcher import clerk_dispatcher
from app.models.user import User
from app.services.user.repository import UserRepository

pytestmark = pytest.mark.integration

TEST_SECRET = "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw"
WEBHOOK_URL = "/api/v1/webhooks/clerk"

USER_DATA = {
    "id": "user_e2e",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "image_url": "https://img.clerk.com/x",
    "public_metadata": {},
    "primary_email_address_id": "idn_1",
    "email_addresses": [{"id": "idn_1", "email_address": "ada@e2e.test", "verification": {"status": "verified"}}],
    "updated_at": 1754000000000,
}


def signed(body: str, msg_id: str = "msg_1") -> dict:
    ts = datetime.now(tz=UTC)
    return {
        "svix-id": msg_id,
        "svix-timestamp": str(int(ts.timestamp())),
        "svix-signature": Webhook(TEST_SECRET).sign(msg_id, ts, body),
        "content-type": "application/json",
    }


def envelope(event_type: str, data: dict) -> str:
    return json.dumps(
        {
            "type": event_type,
            "object": "event",
            "timestamp": int(datetime.now(tz=UTC).timestamp() * 1000),
            "instance_id": "ins_test",
            "data": data,
        }
    )


async def test_unknown_event_type_returns_204(client):
    """Unhandled types must never error — Clerk retries errors and then
    disables the endpoint."""
    body = envelope("session.created", {"id": "sess_1"})
    response = await client.post(WEBHOOK_URL, content=body, headers=signed(body))
    assert response.status_code == 204


async def test_unsigned_request_is_rejected(client):
    body = envelope("user.created", {"id": "user_1"})
    response = await client.post(WEBHOOK_URL, content=body, headers={"content-type": "application/json"})
    assert response.status_code == 401


async def test_tampered_body_is_rejected(client):
    body = envelope("user.created", {"id": "user_1"})
    headers = signed(body)
    tampered = envelope("user.created", {"id": "user_attacker"})
    response = await client.post(WEBHOOK_URL, content=tampered, headers=headers)
    assert response.status_code == 401


async def test_endpoint_requires_no_bearer_token(client):
    """The signature is the credential; no JWT is involved."""
    body = envelope("session.created", {"id": "sess_1"})
    response = await client.post(WEBHOOK_URL, content=body, headers=signed(body))
    assert response.status_code == 204


async def test_registered_handler_is_invoked_with_the_delivery_context(client):
    """A registered handler receives the whole context — payload, delivery id
    and session — and its execution is what produces the 204, not just
    dispatch itself."""
    received = {}

    async def handler(ctx):
        received["ctx"] = ctx

    clerk_dispatcher.register("test.event_ok", handler)
    try:
        body = envelope("test.event_ok", {"id": "abc123"})
        response = await client.post(WEBHOOK_URL, content=body, headers=signed(body, msg_id="msg_ctx"))

        assert response.status_code == 204
        ctx = received["ctx"]
        assert ctx.data == {"id": "abc123"}
        assert ctx.event.type == "test.event_ok"
        # Carried off the svix-id header, not the payload — this is what a
        # dedup table would key on, and what the dispatch log line reports.
        assert ctx.message_id == "msg_ctx"
        assert ctx.session is not None
    finally:
        clerk_dispatcher._handlers.pop("test.event_ok", None)


async def test_handler_exception_propagates_and_is_not_swallowed(client):
    """A failing handler must NOT be swallowed into a 204 — Clerk needs to
    see a failure so it retries. Only an *unregistered* type is a no-op.

    Asserting a 500 status code here is not reliable: Starlette's
    BaseHTTPMiddleware (used by AuthMiddleware and the other middlewares in
    app/api/middlewares/) re-raises route exceptions through
    call_next when driven over httpx's ASGITransport, before the registered
    ServiceError/Exception handlers get a chance to convert it to a
    response — the same limitation documented in
    tests/integration/exceptions/test_handlers.py's
    TestGlobalExceptionHandler. Asserting the raise reaches the caller is
    the reliable way to prove dispatch does not swallow it into 204; behind
    a real ASGI server the same unhandled exception is still turned into a
    500 for Clerk by Starlette's outermost ServerErrorMiddleware.
    """

    async def failing_handler(ctx):
        raise RuntimeError("boom")

    clerk_dispatcher.register("test.event_fail", failing_handler)
    try:
        body = envelope("test.event_fail", {"id": "x"})
        with pytest.raises(RuntimeError, match="boom"):
            await client.post(WEBHOOK_URL, content=body, headers=signed(body))
    finally:
        clerk_dispatcher._handlers.pop("test.event_fail", None)


# ============================================================================
# Handler sequences against a real database
#
# The unit tests already prove each handler's logic against mocked
# repositories. These exercise what a mock cannot: a row actually landing,
# surviving a replay unduplicated, and converging correctly when two
# handlers touch the same user in sequence.
# ============================================================================


async def post(client: AsyncClient, event_type: str, data: dict, msg_id: str = "msg_e2e") -> Response:
    """POST one signed webhook event via the given client."""
    body = envelope(event_type, data)
    return await client.post(WEBHOOK_URL, content=body, headers=signed(body, msg_id=msg_id))


@pytest.fixture(autouse=True)
def clerk_has_the_user():
    """Stub the Clerk lookup the create handler now makes before inserting.

    Without this the suite would issue a real Backend API call per new user.
    True is the answer for every legitimate delivery — Clerk fires
    user.created only once it holds the user — so defaulting to it keeps
    these sequences exercising the path they were written for.
    """
    with patch(
        "app.services.user.service.user_service.exists_in_clerk",
        new=AsyncMock(return_value=True),
    ) as stub:
        yield stub


@pytest.fixture
def mocked_memory():
    """Stub mem0 for user.deleted's erasure cascade.

    delete_user_memory() swallows its own exceptions (see
    app/agents/shared/memory/factory.py), so leaving it unmocked would not
    fail the test — but it would try to build a real AsyncMemory against
    whatever OpenAI/pgvector config is in the test environment, which is
    slow and produces noisy exception logs. Mirrors the pattern already used
    by tests/integration/api/test_auth_delete.py.
    """
    with patch("app.services.user.service.delete_user_memory", new=AsyncMock()) as memory:
        yield memory


async def test_user_created_persists_the_row(client, db_session):
    """A real row is written and independently readable, not merely a mock
    call recorded."""
    response = await post(client, "user.created", USER_DATA)
    assert response.status_code == 204

    user = await UserRepository.get_by_clerk_id(db_session, "user_e2e")
    assert user is not None
    assert user.email == "ada@e2e.test"


async def test_user_created_replayed_does_not_duplicate(client, db_session):
    """There is no dedup table — idempotency on replay is the whole defence."""
    await post(client, "user.created", USER_DATA, msg_id="msg_a")
    await post(client, "user.created", USER_DATA, msg_id="msg_b")

    result = await db_session.execute(select(User).where(User.clerk_id == "user_e2e"))
    assert len(result.scalars().all()) == 1


async def test_create_declines_when_clerk_no_longer_has_the_user(client, db_session, clerk_has_the_user):
    """A delivery redelivered after the user was erased must write nothing.

    erase_user() rewrites clerk_id and releases the email, so the erased row
    is unreachable by the payload's id — the handler cannot tell "erased"
    from "create has not landed yet" on its own, and the payload carries the
    email and names it would re-insert. Clerk is the authority that settles
    it.
    """
    clerk_has_the_user.return_value = False

    assert (await post(client, "user.created", USER_DATA)).status_code == 204

    result = await db_session.execute(select(User).where(User.clerk_id == "user_e2e"))
    assert result.scalars().all() == []


async def test_stale_update_does_not_overwrite_newer_data(client, db_session):
    """Clerk guarantees no delivery ordering; a stale update arriving after a
    newer one must not win."""
    await post(client, "user.created", USER_DATA)

    newer = {**USER_DATA, "first_name": "Newer", "updated_at": 1754000009000}
    stale = {**USER_DATA, "first_name": "Stale", "updated_at": 1753000000000}

    await post(client, "user.updated", newer, msg_id="msg_new")
    await post(client, "user.updated", stale, msg_id="msg_old")

    user = await UserRepository.get_by_clerk_id(db_session, "user_e2e")
    assert user.first_name == "Newer"


async def test_user_deleted_anonymises_and_replay_is_a_noop(client, db_session, mocked_memory):
    """The erasure cascade runs end-to-end and leaves no PII in the row; a
    replay (or the echo of our own DELETE /me) must not error."""
    await post(client, "user.created", USER_DATA)
    created = await UserRepository.get_by_clerk_id(db_session, "user_e2e")
    internal_id = created.id

    assert (await post(client, "user.deleted", {"id": "user_e2e", "deleted": True})).status_code == 204
    assert await UserRepository.get_by_clerk_id(db_session, "user_e2e") is None

    anonymised = await UserRepository.get_by_id(db_session, internal_id)
    assert anonymised is not None
    assert anonymised.clerk_id != "user_e2e"
    assert anonymised.email != "ada@e2e.test"
    assert anonymised.first_name is None
    assert anonymised.last_name is None
    assert anonymised.avatar_url is None
    assert anonymised.anonymized_at is not None

    # Replay — and the echo of our own DELETE /me — must not error.
    assert (
        await post(client, "user.deleted", {"id": "user_e2e", "deleted": True}, msg_id="msg_replay")
    ).status_code == 204


async def test_user_updated_after_deletion_does_not_resurrect(client, db_session, mocked_memory):
    """An unknown clerk_id is indistinguishable from an erased one, so
    user.updated must decline to create a row rather than resurrect."""
    await post(client, "user.created", USER_DATA)
    await post(client, "user.deleted", {"id": "user_e2e", "deleted": True})

    assert (await post(client, "user.updated", USER_DATA, msg_id="msg_after")).status_code == 204

    result = await db_session.execute(select(User).where(User.clerk_id == "user_e2e"))
    assert result.scalars().all() == []
