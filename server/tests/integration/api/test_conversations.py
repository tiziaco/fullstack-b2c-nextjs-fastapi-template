"""Integration tests for conversation CRUD API endpoints."""

import uuid

import pytest

from app.models.conversation import Conversation

pytestmark = pytest.mark.integration


@pytest.fixture
async def user_conversation(db_session, test_user):
    """An existing conversation owned by test_user."""
    conv = Conversation(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        name="Existing Chat",
    )
    db_session.add(conv)
    await db_session.flush()
    await db_session.refresh(conv)
    return conv


class TestCreateConversation:
    """Tests for POST /api/v1/conversation/conversation"""

    async def test_unauthenticated_returns_401(self, client):
        response = await client.post("/api/v1/conversation/conversation")
        assert response.status_code == 401

    async def test_creates_conversation_returns_200(self, authenticated_client):
        response = await authenticated_client.post("/api/v1/conversation/conversation")
        assert response.status_code == 200

    async def test_response_has_conversation_id(self, authenticated_client):
        response = await authenticated_client.post("/api/v1/conversation/conversation")
        data = response.json()
        assert "conversation_id" in data
        # Should be a valid UUID
        uuid.UUID(data["conversation_id"])  # raises ValueError if invalid

    async def test_response_schema(self, authenticated_client):
        response = await authenticated_client.post("/api/v1/conversation/conversation")
        data = response.json()
        assert "conversation_id" in data
        assert "name" in data
        assert "created_at" in data


class TestListConversations:
    """Tests for GET /api/v1/conversation/conversations"""

    async def test_unauthenticated_returns_401(self, client):
        response = await client.get("/api/v1/conversation/conversations")
        assert response.status_code == 401

    async def test_empty_list_for_new_user(self, authenticated_client):
        response = await authenticated_client.get("/api/v1/conversation/conversations")
        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_user_conversations(self, authenticated_client, user_conversation):
        response = await authenticated_client.get("/api/v1/conversation/conversations")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["conversation_id"] == user_conversation.id


class TestRenameConversation:
    """Tests for PATCH /api/v1/conversation/conversation/{id}/name"""

    async def test_unauthenticated_returns_401(self, client, user_conversation):
        response = await client.patch(
            f"/api/v1/conversation/conversation/{user_conversation.id}/name",
            data={"name": "New Name"},
        )
        assert response.status_code == 401

    async def test_rename_succeeds(self, authenticated_client, user_conversation):
        response = await authenticated_client.patch(
            f"/api/v1/conversation/conversation/{user_conversation.id}/name",
            data={"name": "Renamed Chat"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Renamed Chat"
        assert data["conversation_id"] == user_conversation.id

    async def test_rename_nonexistent_returns_404(self, authenticated_client):
        response = await authenticated_client.patch(
            "/api/v1/conversation/conversation/nonexistent-id/name",
            data={"name": "New Name"},
        )
        assert response.status_code == 404

    async def test_rename_other_users_conversation_returns_403(self, db_session, authenticated_client):
        from app.models.user import User

        other_user = User(clerk_id="clerk_other_conv", email="other_conv@example.com")
        db_session.add(other_user)
        await db_session.flush()
        await db_session.refresh(other_user)

        other_conv = Conversation(
            id=str(uuid.uuid4()),
            user_id=other_user.id,
            name="Other's Chat",
        )
        db_session.add(other_conv)
        await db_session.flush()

        response = await authenticated_client.patch(
            f"/api/v1/conversation/conversation/{other_conv.id}/name",
            data={"name": "Hijacked"},
        )
        assert response.status_code == 403


class TestDeleteConversation:
    """Tests for DELETE /api/v1/conversation/conversation/{id}"""

    async def test_unauthenticated_returns_401(self, client, user_conversation):
        response = await client.delete(f"/api/v1/conversation/conversation/{user_conversation.id}")
        assert response.status_code == 401

    async def test_delete_succeeds(self, authenticated_client_with_agent, user_conversation, stub_checkpoint_deletion):
        response = await authenticated_client_with_agent.delete(
            f"/api/v1/conversation/conversation/{user_conversation.id}"
        )
        assert response.status_code == 204

    async def test_delete_nonexistent_returns_404(self, authenticated_client_with_agent):
        response = await authenticated_client_with_agent.delete(
            "/api/v1/conversation/conversation/nonexistent-conv-id"
        )
        assert response.status_code == 404

    async def test_delete_other_users_conversation_returns_403(self, db_session, authenticated_client_with_agent):
        from app.models.user import User

        other_user = User(clerk_id="clerk_other_del", email="other_del@example.com")
        db_session.add(other_user)
        await db_session.flush()
        await db_session.refresh(other_user)

        other_conv = Conversation(
            id=str(uuid.uuid4()),
            user_id=other_user.id,
            name="Other's Chat",
        )
        db_session.add(other_conv)
        await db_session.flush()

        response = await authenticated_client_with_agent.delete(f"/api/v1/conversation/conversation/{other_conv.id}")
        assert response.status_code == 403
