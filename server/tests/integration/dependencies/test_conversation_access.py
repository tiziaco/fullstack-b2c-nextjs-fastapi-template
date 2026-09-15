"""Integration tests for get_user_conversation dependency — ownership enforcement."""

import uuid

import pytest

from app.models.conversation import Conversation
from app.models.user import User

pytestmark = pytest.mark.integration


class TestConversationAccessDependency:
    """Tests for get_user_conversation dependency via API calls."""

    async def test_nonexistent_conversation_returns_404(self, authenticated_client):
        """Conversation not in DB → 404 from ConversationNotFoundError."""
        fake_id = str(uuid.uuid4())
        response = await authenticated_client.patch(
            f"/api/v1/conversation/conversation/{fake_id}/name",
            data={"name": "New Name"},
        )
        assert response.status_code == 404

    async def test_error_response_has_error_code(self, authenticated_client):
        """404 response body contains error code for client identification."""
        fake_id = str(uuid.uuid4())
        response = await authenticated_client.patch(
            f"/api/v1/conversation/conversation/{fake_id}/name",
            data={"name": "New Name"},
        )
        data = response.json()
        assert "error" in data
        assert data["error"] == "CONVERSATION_NOT_FOUND"

    async def test_other_users_conversation_returns_403(self, db_session, authenticated_client):
        """Conversation exists but belongs to different user → 403."""
        other_user = User(
            clerk_id="clerk_access_other",
            email="access_other@example.com",
        )
        db_session.add(other_user)
        await db_session.flush()
        await db_session.refresh(other_user)

        other_conv = Conversation(
            id=str(uuid.uuid4()),
            user_id=other_user.id,
            name="Not Mine",
        )
        db_session.add(other_conv)
        await db_session.flush()

        response = await authenticated_client.patch(
            f"/api/v1/conversation/conversation/{other_conv.id}/name",
            data={"name": "Hijack"},
        )
        assert response.status_code == 403

    async def test_access_denied_error_code_in_response(self, db_session, authenticated_client):
        """403 response body contains CONVERSATION_ACCESS_DENIED error code."""
        other_user = User(
            clerk_id="clerk_access_denied",
            email="access_denied@example.com",
        )
        db_session.add(other_user)
        await db_session.flush()
        await db_session.refresh(other_user)

        other_conv = Conversation(
            id=str(uuid.uuid4()),
            user_id=other_user.id,
            name="Not Mine",
        )
        db_session.add(other_conv)
        await db_session.flush()

        response = await authenticated_client.patch(
            f"/api/v1/conversation/conversation/{other_conv.id}/name",
            data={"name": "Hijack"},
        )
        data = response.json()
        assert data["error"] == "CONVERSATION_ACCESS_DENIED"

    async def test_own_conversation_succeeds(self, authenticated_client, db_session, test_user):
        """Accessing own conversation → 200, no error."""
        conv = Conversation(
            id=str(uuid.uuid4()),
            user_id=test_user.id,
            name="Mine",
        )
        db_session.add(conv)
        await db_session.flush()

        response = await authenticated_client.patch(
            f"/api/v1/conversation/conversation/{conv.id}/name",
            data={"name": "Still Mine"},
        )
        assert response.status_code == 200
