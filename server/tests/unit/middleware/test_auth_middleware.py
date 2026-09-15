"""Tests for app.api.middlewares.auth — token extraction and permissive pass-through."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.api.middlewares.auth import AuthMiddleware

pytestmark = pytest.mark.unit


def _make_app():
    """Create a minimal Starlette app with AuthMiddleware for testing."""

    async def endpoint(request: Request):
        return JSONResponse(
            {
                "clerk_id": getattr(request.state, "clerk_id", None),
                "user_id": getattr(request.state, "user_id", None),
                "role": getattr(request.state, "role", None),
            }
        )

    app = Starlette(routes=[Route("/test", endpoint)])
    app.add_middleware(AuthMiddleware)
    return app


@pytest.fixture
def app():
    return _make_app()


class TestAuthMiddleware:
    """Tests for AuthMiddleware.dispatch()."""

    @pytest.mark.asyncio
    @patch("app.api.middlewares.auth.clerk_jwt_verifier")
    async def test_valid_bearer_sets_clerk_id(self, mock_verifier, app):
        mock_verifier.verify_token.return_value = {"sub": "user_abc123"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/test", headers={"Authorization": "Bearer valid.token"})

        assert response.status_code == 200
        assert response.json()["clerk_id"] == "user_abc123"

    @pytest.mark.asyncio
    async def test_missing_auth_header_passes_through(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/test")

        assert response.status_code == 200
        assert response.json()["clerk_id"] is None

    @pytest.mark.asyncio
    @patch("app.api.middlewares.auth.clerk_jwt_verifier")
    async def test_invalid_token_clerk_id_none(self, mock_verifier, app):
        mock_verifier.verify_token.return_value = None

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/test", headers={"Authorization": "Bearer bad.token"})

        assert response.status_code == 200
        assert response.json()["clerk_id"] is None

    @pytest.mark.asyncio
    async def test_non_bearer_auth_header_ignored(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/test", headers={"Authorization": "Basic dXNlcjpwYXNz"})

        assert response.status_code == 200
        assert response.json()["clerk_id"] is None

    @pytest.mark.asyncio
    async def test_bearer_without_token_clerk_id_none(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/test", headers={"Authorization": "Bearer "})

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_user_id_defaults_to_none(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/test")

        assert response.json()["user_id"] is None

    # --- NEW: org claims ---

    @pytest.mark.asyncio
    @patch("app.api.middlewares.auth.clerk_jwt_verifier")
    async def test_role_claim_extracted_from_token(self, mock_verifier, app):
        """The custom `role` claim is sourced from Clerk publicMetadata.role."""
        mock_verifier.verify_token.return_value = {"sub": "user_abc123", "role": "admin"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/test", headers={"Authorization": "Bearer valid.token"})

        assert response.json()["role"] == "admin"

    @pytest.mark.asyncio
    @patch("app.api.middlewares.auth.clerk_jwt_verifier")
    async def test_role_claim_not_prefix_stripped(self, mock_verifier, app):
        """The role claim is stored verbatim, with no prefix stripped or added."""
        mock_verifier.verify_token.return_value = {"sub": "user_u1", "role": "user"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/test", headers={"Authorization": "Bearer token"})

        assert response.json()["role"] == "user"

    @pytest.mark.asyncio
    @patch("app.api.middlewares.auth.clerk_jwt_verifier")
    async def test_missing_role_claim_is_none(self, mock_verifier, app):
        """A token with no role claim leaves request.state.role unset."""
        mock_verifier.verify_token.return_value = {"sub": "user_abc123"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/test", headers={"Authorization": "Bearer valid.token"})

        assert response.json()["role"] is None
