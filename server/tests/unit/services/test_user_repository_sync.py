"""last_synced_at must carry Clerk's clock, not ours.

The ordering guard compares an event's updated_at against this column. If
one side is our wall clock and the other is Clerk's, host clock skew
silently corrupts every comparison — and skew in one direction drops
legitimate updates indefinitely.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.user import User
from app.services.user.repository import UserRepository

pytestmark = pytest.mark.unit

CLERK_TS = datetime(2022, 5, 31, 15, 56, 31, tzinfo=UTC)


@pytest.fixture
def session() -> AsyncMock:
    s = AsyncMock()
    s.add = MagicMock()
    return s


async def test_create_uses_supplied_clerk_timestamp(session):
    user = await UserRepository.create(
        session=session,
        clerk_id="user_abc",
        email="a@b.com",
        last_synced_at=CLERK_TS,
    )
    assert user.last_synced_at == CLERK_TS


async def test_create_falls_back_to_now_when_absent(session):
    before = datetime.now(UTC)
    user = await UserRepository.create(session=session, clerk_id="user_abc", email="a@b.com")
    assert user.last_synced_at >= before


async def test_update_from_clerk_uses_supplied_timestamp(session):
    user = User(clerk_id="user_abc", email="a@b.com")
    user.last_synced_at = CLERK_TS - timedelta(days=1)

    await UserRepository.update_from_clerk(session=session, user=user, first_name="New", last_synced_at=CLERK_TS)
    assert user.last_synced_at == CLERK_TS


async def test_update_from_clerk_falls_back_to_now(session):
    user = User(clerk_id="user_abc", email="a@b.com")
    before = datetime.now(UTC)

    await UserRepository.update_from_clerk(session=session, user=user, first_name="New")
    assert user.last_synced_at >= before
