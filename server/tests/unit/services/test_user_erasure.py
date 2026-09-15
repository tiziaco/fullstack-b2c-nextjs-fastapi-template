"""Tests for UserService.erase_user — the shared GDPR cascade.

Used by both DELETE /api/v1/auth/me and the user.deleted webhook, so the
ordering of its steps is contractual: checkpoints and memories must be
cleared before the row is anonymised, because anonymisation destroys the
identifiers those systems are keyed by.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.user import User
from app.services.user.service import UserService

pytestmark = pytest.mark.unit


def make_user() -> User:
    user = User(
        id="11111111-2222-3333-4444-555555555555",
        clerk_id="user_abc",
        email="person@example.com",
    )
    user.conversations = []
    return user


@pytest.fixture
def session() -> AsyncMock:
    s = AsyncMock()
    s.add = MagicMock()
    return s


async def test_erase_user_runs_full_cascade(session):
    user = make_user()

    with (
        patch(
            "app.services.user.service.conversation_service.soft_delete_all_user_conversations",
            new=AsyncMock(return_value=["conv_1", "conv_2"]),
        ),
        patch("app.services.user.service.delete_conversation_checkpoints", new=AsyncMock()) as checkpoints,
        patch("app.services.user.service.delete_user_memory", new=AsyncMock()) as mem,
    ):
        await UserService().erase_user(user, session)

    assert checkpoints.await_count == 2
    mem.assert_awaited_once_with("11111111-2222-3333-4444-555555555555")
    session.commit.assert_awaited_once()


async def test_erase_user_anonymizes_the_row(session):
    user = make_user()

    with (
        patch(
            "app.services.user.service.conversation_service.soft_delete_all_user_conversations",
            new=AsyncMock(return_value=[]),
        ),
        patch("app.services.user.service.delete_user_memory", new=AsyncMock()),
    ):
        await UserService().erase_user(user, session)

    assert user.clerk_id != "user_abc"
    assert user.email.endswith("@anonymized.local")
    assert user.anonymized_at is not None


async def test_erase_user_clears_checkpoints_and_memory_before_anonymising(session):
    """Step order is contractual, not incidental.

    anonymize_user() rewrites clerk_id, and the LangGraph checkpoint store and
    mem0 memory are both keyed by identifiers that exist only before that
    rewrite. If anonymize_user() ever ran first, checkpoint/memory cleanup
    would silently no-op against the wrong (or already-gone) identifiers —
    a regression the outcome-based tests above would NOT catch, since they
    only assert final call counts and end state, not sequence. This is also
    the exact guarantee the user.deleted webhook handler will depend on.
    """
    user = make_user()

    parent = MagicMock()
    checkpoints_mock = AsyncMock()
    parent.attach_mock(checkpoints_mock, "delete_conversation_checkpoints")

    delete_memory_mock = AsyncMock()
    parent.attach_mock(delete_memory_mock, "delete_user_memory")

    anonymize_mock = MagicMock()
    parent.attach_mock(anonymize_mock, "anonymize_user")

    with (
        patch(
            "app.services.user.service.conversation_service.soft_delete_all_user_conversations",
            new=AsyncMock(return_value=["conv_1"]),
        ),
        patch("app.services.user.service.delete_conversation_checkpoints", new=checkpoints_mock),
        patch("app.services.user.service.delete_user_memory", new=delete_memory_mock),
        patch.object(User, "anonymize_user", new=anonymize_mock),
    ):
        await UserService().erase_user(user, session)

    call_order = [call[0] for call in parent.mock_calls]
    assert call_order.index("delete_conversation_checkpoints") < call_order.index("anonymize_user")
    assert call_order.index("delete_user_memory") < call_order.index("anonymize_user")
