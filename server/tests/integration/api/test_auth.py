"""Integration tests for GET /api/v1/auth/me — authentication and user profile."""

import pytest

pytestmark = pytest.mark.integration


class TestGetMe:
    """Tests for GET /api/v1/auth/me"""

    async def test_unauthenticated_returns_401(self, client):
        """No auth header → middleware sets clerk_id=None → get_clerk_id raises 401."""
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401

    async def test_authenticated_returns_200(self, authenticated_client):
        response = await authenticated_client.get("/api/v1/auth/me")
        assert response.status_code == 200

    async def test_response_contains_user_fields(self, authenticated_client, test_user):
        response = await authenticated_client.get("/api/v1/auth/me")
        data = response.json()

        assert data["id"] == test_user.id
        assert data["clerk_id"] == test_user.clerk_id
        assert data["email"] == test_user.email

    async def test_response_schema_has_required_fields(self, authenticated_client):
        response = await authenticated_client.get("/api/v1/auth/me")
        data = response.json()

        for field in ["id", "clerk_id", "email", "created_at"]:
            assert field in data, f"Missing field: {field}"

    async def test_optional_fields_present_or_null(self, authenticated_client):
        response = await authenticated_client.get("/api/v1/auth/me")
        data = response.json()
        # These keys should be present (may be None)
        assert "first_name" in data
        assert "last_name" in data
        assert "avatar_url" in data
