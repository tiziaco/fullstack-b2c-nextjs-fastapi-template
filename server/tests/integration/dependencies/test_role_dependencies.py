"""Integration tests for role-based access control dependencies."""

import pytest
from fastapi import APIRouter

from app.api.dependencies.authentication import get_current_role
from app.api.dependencies.authorization import AdminOnly
from app.main import app
from app.models.enums import Role

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module", autouse=True)
def role_test_routes():
    """Mount a sentinel endpoint with a role guard for the duration of this module."""
    router = APIRouter(prefix="/_test/rbac")

    @router.get("/admin-only", dependencies=[AdminOnly])
    async def _admin():
        return {"ok": True}

    original_routes = list(app.router.routes)
    app.include_router(router)
    yield
    app.router.routes[:] = original_routes


def _set_role(role: Role) -> None:
    app.dependency_overrides[get_current_role] = lambda: role


class TestAdminOnly:
    async def test_admin_passes(self, authenticated_client):
        _set_role(Role.ADMIN)
        response = await authenticated_client.get("/_test/rbac/admin-only")
        assert response.status_code == 200

    async def test_user_blocked(self, authenticated_client):
        _set_role(Role.USER)
        response = await authenticated_client.get("/_test/rbac/admin-only")
        assert response.status_code == 403


class TestMissingRole:
    async def test_no_role_returns_403(self, client):
        # No get_current_role override — request.state.role is None,
        # so get_current_role raises AuthorizationError -> 403.
        response = await client.get("/_test/rbac/admin-only")
        assert response.status_code == 403
