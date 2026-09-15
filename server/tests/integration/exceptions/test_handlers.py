"""Integration tests for exception handlers — HTTP response mapping, no info leakage."""

import uuid

import pytest

from app.models.conversation import Conversation

pytestmark = pytest.mark.integration


class TestServiceErrorHandler:
    """Tests for service_exception_handler — ServiceError → HTTP response."""

    async def test_not_found_error_returns_404(self, authenticated_client):
        """ConversationNotFoundError (NotFoundError subclass) → 404."""
        response = await authenticated_client.patch(
            f"/api/v1/conversation/conversation/{uuid.uuid4()}/name",
            data={"name": "X"},
        )
        assert response.status_code == 404

    async def test_not_found_response_has_error_code(self, authenticated_client):
        response = await authenticated_client.patch(
            f"/api/v1/conversation/conversation/{uuid.uuid4()}/name",
            data={"name": "X"},
        )
        data = response.json()
        assert "error" in data
        assert "message" in data
        assert "correlation_id" in data

    async def test_access_denied_returns_403(self, db_session, authenticated_client):
        """ConversationAccessDeniedError (AuthorizationError subclass) → 403."""
        from app.models.user import User

        other_user = User(clerk_id="clerk_handler_other", email="handler_other@example.com")
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

        response = await authenticated_client.delete(f"/api/v1/conversation/conversation/{other_conv.id}")
        assert response.status_code == 403

    async def test_unauthenticated_returns_401(self, client):
        """AuthenticationError (no clerk_id) → 401."""
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401
        data = response.json()
        assert "error" in data
        assert data["error"] == "AUTHENTICATION_ERROR"


class TestValidationErrorHandler:
    """Tests for validation_exception_handler — Pydantic RequestValidationError → 422."""

    async def test_invalid_payload_returns_422(self, authenticated_client_with_agent, db_session, test_user):
        """Sending a message that violates schema constraints → 422."""
        conv = Conversation(
            id=str(uuid.uuid4()),
            user_id=test_user.id,
            name="Test",
        )
        db_session.add(conv)
        await db_session.flush()

        response = await authenticated_client_with_agent.post(
            f"/api/v1/chatbot/chat/{conv.id}",
            json={"message": ""},  # empty → min_length=1 violation
        )
        assert response.status_code == 422

    async def test_422_response_has_field_errors(self, authenticated_client_with_agent, db_session, test_user):
        conv = Conversation(
            id=str(uuid.uuid4()),
            user_id=test_user.id,
            name="Test",
        )
        db_session.add(conv)
        await db_session.flush()

        response = await authenticated_client_with_agent.post(
            f"/api/v1/chatbot/chat/{conv.id}",
            json={"message": ""},
        )
        data = response.json()
        assert "errors" in data or "detail" in data


class TestGlobalExceptionHandler:
    """Tests for global_exception_handler — returns 500 without leaking details.

    Called directly because Starlette's BaseHTTPMiddleware (used by Prometheus)
    re-raises route exceptions via call_next before FastAPI's handler layer runs.
    Testing the handler function directly is the reliable, middleware-independent approach.
    """

    async def test_unhandled_exception_returns_500(self):
        """RuntimeError passed to handler → 500 JSONResponse."""
        from unittest.mock import MagicMock

        from app.exceptions.handlers import global_exception_handler

        mock_request = MagicMock()
        mock_request.url.path = "/api/v1/auth/me"
        mock_request.method = "GET"
        mock_request.client.host = "127.0.0.1"

        response = await global_exception_handler(mock_request, RuntimeError("unexpected internal error"))

        assert response.status_code == 500

    async def test_500_response_does_not_expose_stack_trace(self):
        """500 response must not include Python tracebacks or internal details."""
        import json
        from unittest.mock import MagicMock

        from app.exceptions.handlers import global_exception_handler

        mock_request = MagicMock()
        mock_request.url.path = "/api/v1/auth/me"
        mock_request.method = "GET"
        mock_request.client.host = "127.0.0.1"

        response = await global_exception_handler(mock_request, RuntimeError("secret internal detail"))

        data = json.loads(response.body)
        response_text = str(data)
        assert "Traceback" not in response_text
        assert "secret internal detail" not in response_text
        assert "RuntimeError" not in response_text
