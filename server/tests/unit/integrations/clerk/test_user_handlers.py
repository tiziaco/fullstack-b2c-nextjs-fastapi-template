"""Tests for the user.* webhook handlers.

Two invariants are load-bearing and tested explicitly:

1. Idempotency. There is no dedup table, so a replay within svix's
   five-minute tolerance must converge, not duplicate.
2. Never resurrect. An unknown clerk_id is ambiguous — the create event may
   not have landed, or the user may have been erased (anonymize_user
   rewrites clerk_id, so the two are indistinguishable). user.updated
   declines outright; user.created resolves the ambiguity by asking Clerk,
   and inserts only for a user Clerk still holds.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.clerk import ClerkRateLimitError
from app.integrations.clerk.timestamps import UNSYNCED_EPOCH
from app.integrations.clerk.webhooks.handlers.user import (
    handle_user_created,
    handle_user_deleted,
    handle_user_updated,
    is_primary_email_verified,
    primary_email_from_payload,
)
from app.integrations.clerk.webhooks.schemas import (
    ClerkEvent,
    WebhookContext,
)
from app.models.user import User

pytestmark = pytest.mark.unit

NOW_MS = 1754000000000
NOW_DT = datetime.fromtimestamp(NOW_MS / 1000, tz=UTC)

USER_PAYLOAD = {
    "id": "user_abc",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "image_url": "https://img.clerk.com/x",
    "public_metadata": {},
    "primary_email_address_id": "idn_1",
    "email_addresses": [
        {
            "id": "idn_2",
            "email_address": "other@example.com",
            "verification": {"status": "unverified"},
        },
        {
            "id": "idn_1",
            "email_address": "ada@example.com",
            "verification": {"status": "verified"},
        },
    ],
    "updated_at": NOW_MS,
}


def ctx(data: dict, session, event_type: str = "user.created") -> WebhookContext:
    """Wrap a raw payload in the context handlers now receive.

    Handlers read only `ctx.data` and `ctx.session`, so the event type and
    message id are placeholders except where a test asserts on them.
    """
    return WebhookContext(
        event=ClerkEvent(type=event_type, data=data),
        message_id="msg_test",
        session=session,
    )


@pytest.fixture
def session() -> AsyncMock:
    s = AsyncMock()
    s.add = MagicMock()
    return s


@pytest.fixture(autouse=True)
def clerk_has_the_user() -> AsyncMock:
    """Creating a row now confirms the user still exists in Clerk.

    Answering True by default keeps every other test exercising the path it
    was written for. The tests that care flip it, raise from it, or assert it
    was never asked.
    """
    with patch(
        "app.services.user.service.user_service.exists_in_clerk",
        new=AsyncMock(return_value=True),
    ) as stub:
        yield stub


def existing_user(last_synced_at: datetime = NOW_DT) -> User:
    user = User(id="uuid-1", clerk_id="user_abc", email="ada@example.com")
    user.last_synced_at = last_synced_at
    return user


def test_primary_email_picks_the_primary_address():
    assert primary_email_from_payload(USER_PAYLOAD) == "ada@example.com"


def test_primary_email_returns_none_when_absent():
    assert primary_email_from_payload({"email_addresses": []}) is None


def test_email_verified_reads_the_primary_address_only():
    assert is_primary_email_verified(USER_PAYLOAD) is True
    unverified = {
        **USER_PAYLOAD,
        "email_addresses": [{"id": "idn_1", "email_address": "a@b.c", "verification": {"status": "unverified"}}],
    }
    assert is_primary_email_verified(unverified) is False


async def test_user_created_inserts_with_clerk_timestamp(session):
    with (
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.get_by_clerk_id",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.create_or_get",
            new=AsyncMock(return_value=existing_user()),
        ) as create,
    ):
        await handle_user_created(ctx(USER_PAYLOAD, session))

    kwargs = create.await_args.kwargs
    assert kwargs["email"] == "ada@example.com"
    assert kwargs["last_synced_at"] == NOW_DT


async def test_user_created_insert_seeds_epoch_when_timestamp_unusable(session):
    """Regression for the whole-branch review's Important 1: the insert
    branch must never pass last_synced_at=None through to the repository —
    UserRepository.create() falls back to datetime.now(UTC) for None, which
    is exactly the host-clock contamination _apply_profile and UNSYNCED_EPOCH
    both exist to prevent. A fast host clock would then make every
    subsequent user.updated for this row look stale forever."""
    payload_without_timestamp = {**USER_PAYLOAD, "updated_at": None}
    with (
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.get_by_clerk_id",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.create_or_get",
            new=AsyncMock(return_value=existing_user()),
        ) as create,
    ):
        await handle_user_created(ctx(payload_without_timestamp, session))

    kwargs = create.await_args.kwargs
    assert kwargs["last_synced_at"] == UNSYNCED_EPOCH
    assert kwargs["last_synced_at"] is not None


async def test_user_created_declines_when_clerk_no_longer_has_the_user(session, clerk_has_the_user):
    """The resurrection guard: a delivery retried after the user was erased.

    anonymize_user() rewrites clerk_id, so the erased row is unreachable by
    the payload's id and looks like a user who never existed. Creating from
    the payload would put the erased email and names back in the database —
    the asymmetry handle_user_updated already declines on.
    """
    clerk_has_the_user.return_value = False
    with (
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.get_by_clerk_id",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.create_or_get",
            new=AsyncMock(),
        ) as create,
    ):
        await handle_user_created(ctx(USER_PAYLOAD, session))

    create.assert_not_awaited()


async def test_user_created_propagates_an_inconclusive_clerk_error(session, clerk_has_the_user):
    """Only a 404 is an answer. Anything else must earn a redelivery.

    Swallowing a rate limit here would return 204, and svix would consider
    the delivery done — the user would be lost rather than retried.
    """
    clerk_has_the_user.side_effect = ClerkRateLimitError("rate limited", clerk_id="user_abc")
    with (
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.get_by_clerk_id",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.create_or_get",
            new=AsyncMock(),
        ) as create,
        pytest.raises(ClerkRateLimitError),
    ):
        await handle_user_created(ctx(USER_PAYLOAD, session))

    create.assert_not_awaited()


async def test_user_created_on_existing_row_applies_as_update(session, clerk_has_the_user):
    user = existing_user(last_synced_at=NOW_DT - timedelta(hours=1))
    with (
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.get_by_clerk_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.create_or_get",
            new=AsyncMock(),
        ) as create,
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.update_from_clerk",
            new=AsyncMock(return_value=user),
        ) as update,
    ):
        await handle_user_created(ctx(USER_PAYLOAD, session))

    create.assert_not_awaited()
    update.assert_awaited_once()
    # The row was already there, so the existence check never runs. This is
    # what keeps the Clerk lookup at ~one call per new user; moving it above
    # get_by_clerk_id would make it one per delivery.
    clerk_has_the_user.assert_not_awaited()


async def test_user_created_without_an_email_is_skipped(session):
    with patch(
        "app.integrations.clerk.webhooks.handlers.user.user_repository.create_or_get",
        new=AsyncMock(),
    ) as create:
        await handle_user_created(ctx({"id": "user_abc", "email_addresses": []}, session))

    create.assert_not_awaited()


async def test_user_updated_applies_the_profile(session):
    user = existing_user(last_synced_at=NOW_DT - timedelta(hours=1))
    with (
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.get_by_clerk_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.update_from_clerk",
            new=AsyncMock(return_value=user),
        ) as update,
    ):
        await handle_user_updated(ctx(USER_PAYLOAD, session))

    assert update.await_args.kwargs["first_name"] == "Ada"
    assert update.await_args.kwargs["last_synced_at"] == NOW_DT


async def test_user_updated_without_a_usable_timestamp_preserves_last_synced_at(session):
    """A payload with no usable updated_at must not advance last_synced_at
    to the host clock — that would contaminate the ordering guard for every
    later event on this row (see Task 6 fix round 1, Finding 2)."""
    stale_synced_at = NOW_DT - timedelta(hours=1)
    user = existing_user(last_synced_at=stale_synced_at)
    payload_without_timestamp = {**USER_PAYLOAD, "updated_at": None}
    with (
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.get_by_clerk_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.update_from_clerk",
            new=AsyncMock(return_value=user),
        ) as update,
    ):
        await handle_user_updated(ctx(payload_without_timestamp, session))

    # Passed through unchanged, not advanced to datetime.now(UTC).
    assert update.await_args.kwargs["last_synced_at"] == stale_synced_at


async def test_user_updated_never_creates_a_row(session):
    """The never-resurrect invariant."""
    with (
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.get_by_clerk_id",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.create_or_get",
            new=AsyncMock(),
        ) as create,
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.update_from_clerk",
            new=AsyncMock(),
        ) as update,
    ):
        await handle_user_updated(ctx(USER_PAYLOAD, session))

    create.assert_not_awaited()
    update.assert_not_awaited()


async def test_stale_event_is_dropped(session):
    """An event older than what we have synced must not overwrite newer data."""
    user = existing_user(last_synced_at=NOW_DT + timedelta(hours=1))
    with (
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.get_by_clerk_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.update_from_clerk",
            new=AsyncMock(),
        ) as update,
    ):
        await handle_user_updated(ctx(USER_PAYLOAD, session))

    update.assert_not_awaited()


async def test_same_timestamp_still_applies(session):
    """Strict `<` — an identical timestamp is applied rather than risking a
    dropped distinct event. Safe because the write is idempotent."""
    user = existing_user(last_synced_at=NOW_DT)
    with (
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.get_by_clerk_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.update_from_clerk",
            new=AsyncMock(return_value=user),
        ) as update,
    ):
        await handle_user_updated(ctx(USER_PAYLOAD, session))

    update.assert_awaited_once()


async def test_user_deleted_runs_the_erasure_cascade(session):
    user = existing_user()
    with (
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.get_by_clerk_id",
            new=AsyncMock(return_value=user),
        ),
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_service.erase_user",
            new=AsyncMock(),
        ) as erase,
    ):
        await handle_user_deleted(ctx({"id": "user_abc", "deleted": True}, session))

    erase.assert_awaited_once()


async def test_user_deleted_for_unknown_user_is_a_noop(session):
    """The echo of our own DELETE /me, and any replay, lands here."""
    with (
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_repository.get_by_clerk_id",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.integrations.clerk.webhooks.handlers.user.user_service.erase_user",
            new=AsyncMock(),
        ) as erase,
    ):
        await handle_user_deleted(ctx({"id": "user_abc", "deleted": True}, session))

    erase.assert_not_awaited()
