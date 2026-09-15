"""Integration tests for the admin smoke endpoint."""

import pytest

from app.api.dependencies.authentication import get_current_role
from app.main import app
from app.models.enums import Role

pytestmark = pytest.mark.integration


class TestAdminPing:
    async def test_admin_gets_ok(self, authenticated_client):
        app.dependency_overrides[get_current_role] = lambda: Role.ADMIN
        response = await authenticated_client.get("/api/v1/admin/ping")
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    async def test_user_is_forbidden(self, authenticated_client):
        app.dependency_overrides[get_current_role] = lambda: Role.USER
        response = await authenticated_client.get("/api/v1/admin/ping")
        assert response.status_code == 403
