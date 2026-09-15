"""Integration tests for chatbot endpoints — chat, stream, history, clear."""

import json
import uuid

import pytest

from app.models.conversation import Conversation

pytestmark = pytest.mark.integration


@pytest.fixture
async def test_conversation(db_session, test_user):
    """A conversation owned by test_user for chatbot testing."""
    conv = Conversation(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        name="Chat Test",
    )
    db_session.add(conv)
    await db_session.flush()
    await db_session.refresh(conv)
    return conv


class TestChatEndpoint:
    """Tests for POST /api/v1/chatbot/chat/{conversation_id}"""

    async def test_unauthenticated_returns_401(self, client, test_conversation):
        response = await client.post(
            f"/api/v1/chatbot/chat/{test_conversation.id}",
            json={"message": "Hello"},
        )
        assert response.status_code == 401

    async def test_chat_returns_200_with_message(self, authenticated_client_with_agent, test_conversation):
        response = await authenticated_client_with_agent.post(
            f"/api/v1/chatbot/chat/{test_conversation.id}",
            json={"message": "Hello there"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert data["message"]["role"] == "assistant"
        assert data["message"]["content"] == "Hi there!"

    async def test_chat_nonexistent_conversation_returns_404(self, authenticated_client_with_agent):
        response = await authenticated_client_with_agent.post(
            "/api/v1/chatbot/chat/nonexistent-conv-id",
            json={"message": "Hello"},
        )
        assert response.status_code == 404

    async def test_chat_empty_message_returns_422(self, authenticated_client_with_agent, test_conversation):
        response = await authenticated_client_with_agent.post(
            f"/api/v1/chatbot/chat/{test_conversation.id}",
            json={"message": ""},
        )
        assert response.status_code == 422

    async def test_chat_other_users_conversation_returns_403(self, db_session, authenticated_client_with_agent):
        from app.models.user import User

        other_user = User(clerk_id="clerk_chat_other", email="chat_other@example.com")
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

        response = await authenticated_client_with_agent.post(
            f"/api/v1/chatbot/chat/{other_conv.id}",
            json={"message": "Hello"},
        )
        assert response.status_code == 403


class TestStreamChatEndpoint:
    """Tests for POST /api/v1/chatbot/chat/{conversation_id}/stream"""

    async def test_stream_returns_event_stream(self, authenticated_client_with_agent, test_conversation, mock_agent):
        # Override get_stream_response to use an async generator
        async def mock_stream(*args, **kwargs):
            for chunk in ["Hello", " World"]:
                yield chunk

        mock_agent.get_stream_response = mock_stream

        response = await authenticated_client_with_agent.post(
            f"/api/v1/chatbot/chat/{test_conversation.id}/stream",
            json={"message": "Hello"},
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

    async def test_stream_response_contains_sse_data(
        self, authenticated_client_with_agent, test_conversation, mock_agent
    ):
        async def mock_stream(*args, **kwargs):
            for chunk in ["Hi!"]:
                yield chunk

        mock_agent.get_stream_response = mock_stream

        response = await authenticated_client_with_agent.post(
            f"/api/v1/chatbot/chat/{test_conversation.id}/stream",
            json={"message": "Hello"},
        )
        content = response.text
        # SSE format: "data: {...}\n\n"
        assert "data:" in content
        # Parse first event
        first_line = [line for line in content.split("\n") if line.startswith("data:")][0]
        payload = json.loads(first_line.replace("data: ", ""))
        assert "content" in payload
        assert "done" in payload


class TestGetChatHistory:
    """Tests for GET /api/v1/chatbot/chat/{conversation_id}/messages"""

    async def test_unauthenticated_returns_401(self, client, test_conversation):
        response = await client.get(f"/api/v1/chatbot/chat/{test_conversation.id}/messages")
        assert response.status_code == 401

    async def test_returns_conversation_history(self, authenticated_client_with_agent, test_conversation):
        response = await authenticated_client_with_agent.get(f"/api/v1/chatbot/chat/{test_conversation.id}/messages")
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert len(data["messages"]) == 2  # from mock_agent fixture

    async def test_history_messages_have_role_and_content(self, authenticated_client_with_agent, test_conversation):
        response = await authenticated_client_with_agent.get(f"/api/v1/chatbot/chat/{test_conversation.id}/messages")
        messages = response.json()["messages"]
        for msg in messages:
            assert "role" in msg
            assert "content" in msg


class TestClearChatHistory:
    """Tests for DELETE /api/v1/chatbot/chat/{conversation_id}/messages"""

    async def test_unauthenticated_returns_401(self, client, test_conversation):
        response = await client.delete(f"/api/v1/chatbot/chat/{test_conversation.id}/messages")
        assert response.status_code == 401

    async def test_clear_history_returns_204(
        self, authenticated_client_with_agent, test_conversation, stub_checkpoint_deletion
    ):
        response = await authenticated_client_with_agent.delete(
            f"/api/v1/chatbot/chat/{test_conversation.id}/messages"
        )
        assert response.status_code == 204
        assert response.content == b""
