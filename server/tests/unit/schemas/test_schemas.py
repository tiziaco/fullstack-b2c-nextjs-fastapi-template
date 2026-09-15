"""Tests for app.schemas — Pydantic model validation, sanitization, serialization."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.auth import UserResponse
from app.schemas.base import ErrorResponse
from app.schemas.chat import ChatRequest, ChatResponse, ConversationHistory, Message, StreamResponse
from app.schemas.conversation import ConversationResponse

pytestmark = pytest.mark.unit


class TestMessage:
    """Tests for Message schema."""

    def test_valid_user_message(self):
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_valid_assistant_message(self):
        msg = Message(role="assistant", content="Hi there")
        assert msg.role == "assistant"

    def test_valid_system_message(self):
        msg = Message(role="system", content="You are helpful")
        assert msg.role == "system"

    def test_invalid_role_rejected(self):
        with pytest.raises(ValidationError):
            Message(role="admin", content="hello")

    def test_empty_content_rejected(self):
        with pytest.raises(ValidationError):
            Message(role="user", content="")

    def test_script_tag_rejected(self):
        with pytest.raises(ValidationError, match="script"):
            Message(role="user", content="<script>alert('xss')</script>")

    def test_null_bytes_rejected(self):
        with pytest.raises(ValidationError, match="null bytes"):
            Message(role="user", content="hello\0world")

    def test_max_length_boundary(self):
        msg = Message(role="user", content="a" * 3000)
        assert len(msg.content) == 3000

    def test_over_max_length_rejected(self):
        with pytest.raises(ValidationError):
            Message(role="user", content="a" * 3001)

    def test_extra_fields_ignored(self):
        msg = Message(role="user", content="hello", extra_field="ignored")
        assert not hasattr(msg, "extra_field")


class TestChatRequest:
    """Tests for ChatRequest schema."""

    def test_valid_request(self):
        req = ChatRequest(message="Hello, how are you?")
        assert req.message == "Hello, how are you?"

    def test_empty_message_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="")

    def test_over_max_length_rejected(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="a" * 3001)


class TestChatResponse:
    """Tests for ChatResponse schema."""

    def test_valid_response(self):
        msg = Message(role="assistant", content="Hello!")
        resp = ChatResponse(message=msg)
        assert resp.message.content == "Hello!"


class TestConversationHistory:
    """Tests for ConversationHistory schema."""

    def test_valid_history(self):
        messages = [
            Message(role="user", content="Hi"),
            Message(role="assistant", content="Hello!"),
        ]
        history = ConversationHistory(messages=messages)
        assert len(history.messages) == 2


class TestStreamResponse:
    """Tests for StreamResponse schema."""

    def test_defaults(self):
        resp = StreamResponse()
        assert resp.content == ""
        assert resp.done is False

    def test_with_content(self):
        resp = StreamResponse(content="chunk", done=True)
        assert resp.content == "chunk"
        assert resp.done is True


class TestConversationResponse:
    """Tests for ConversationResponse with sanitize_name validator."""

    def test_valid_response(self):
        resp = ConversationResponse(
            conversation_id="abc-123",
            name="My Chat",
            created_at=datetime.now(UTC),
        )
        assert resp.name == "My Chat"

    def test_sanitize_name_strips_angle_brackets(self):
        resp = ConversationResponse(
            conversation_id="abc-123",
            name="<script>alert</script>",
            created_at=datetime.now(UTC),
        )
        assert "<" not in resp.name
        assert ">" not in resp.name

    def test_sanitize_name_strips_special_chars(self):
        resp = ConversationResponse(
            conversation_id="abc-123",
            name='test{name}[0]("val")',
            created_at=datetime.now(UTC),
        )
        for char in "<>{}[]()'\"`":
            assert char not in resp.name

    def test_empty_name_allowed(self):
        resp = ConversationResponse(
            conversation_id="abc-123",
            name="",
            created_at=datetime.now(UTC),
        )
        assert resp.name == ""


class TestUserResponse:
    """Tests for UserResponse schema."""

    def test_valid_user_response(self):
        resp = UserResponse(
            id="uuid-123",
            clerk_id="user_abc",
            email="test@example.com",
            first_name="Alice",
            last_name="Smith",
            avatar_url=None,
            created_at=datetime.now(UTC),
        )
        assert resp.email == "test@example.com"

    def test_optional_fields_default_to_none(self):
        resp = UserResponse(
            id="uuid-123",
            clerk_id="user_abc",
            email="test@example.com",
            created_at=datetime.now(UTC),
        )
        assert resp.first_name is None
        assert resp.last_name is None
        assert resp.avatar_url is None


class TestErrorResponse:
    """Tests for ErrorResponse schema."""

    def test_serialization_without_details(self):
        resp = ErrorResponse(
            error="NOT_FOUND",
            message="Resource not found",
            correlation_id="req-123",
        )
        data = resp.model_dump(exclude_none=True)
        assert "details" not in data
        assert data["error"] == "NOT_FOUND"

    def test_serialization_with_details(self):
        resp = ErrorResponse(
            error="VALIDATION_ERROR",
            message="Invalid input",
            correlation_id="req-456",
            details={"field": "email"},
        )
        data = resp.model_dump()
        assert data["details"] == {"field": "email"}
