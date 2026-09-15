"""Integration tests for UserService — JIT provisioning with mocked Clerk, real DB."""

from unittest.mock import MagicMock, patch

import pytest

from app.integrations.clerk.exceptions import ClerkUserNotFoundError
from app.models.user import User
from app.services.user.service import UserService

pytestmark = pytest.mark.integration


@pytest.fixture
def service():
    return UserService()


@pytest.fixture
async def existing_user(db_session):
    """A user that already exists in the database."""
    user = User(
        clerk_id="clerk_provider_existing",
        email="provider_existing@example.com",
        first_name="Existing",
        last_name="User",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


class TestDbHit:
    """Tests for resolve_user when the user already exists in the DB."""

    async def test_db_hit_returns_user_without_calling_clerk(self, service, db_session, existing_user):
        with patch("app.services.user.service.clerk_client.get_user") as mock_get:
            user = await service.resolve_user(existing_user.clerk_id, db_session)
            mock_get.assert_not_called()

        assert user.id == existing_user.id
        assert user.clerk_id == existing_user.clerk_id


class TestJITProvisioning:
    """Tests for JIT provisioning path — user not in cache or DB."""

    def _make_clerk_user(self, clerk_id, email="jit@example.com"):
        clerk_user = MagicMock()
        clerk_user.first_name = "JIT"
        clerk_user.last_name = "User"
        clerk_user.image_url = None
        clerk_user.primary_email_address_id = "email_abc"
        return clerk_user

    @patch("app.services.user.service.clerk_client.get_primary_email")
    @patch("app.services.user.service.clerk_client.get_user")
    async def test_jit_creates_user_in_db(self, mock_get_user, mock_get_email, service, db_session):
        clerk_id = "clerk_jit_new_001"
        mock_get_user.return_value = self._make_clerk_user(clerk_id)
        mock_get_email.return_value = "jit_new@example.com"

        user = await service.resolve_user(clerk_id, db_session)

        assert user.clerk_id == clerk_id
        assert user.email == "jit_new@example.com"
        assert user.id is not None

    @patch("app.services.user.service.clerk_client.get_user")
    async def test_clerk_not_found_raises(self, mock_get_user, service, db_session):
        mock_get_user.side_effect = ClerkUserNotFoundError("not found")

        with pytest.raises(ClerkUserNotFoundError):
            await service.resolve_user("clerk_nonexistent_jit", db_session)
