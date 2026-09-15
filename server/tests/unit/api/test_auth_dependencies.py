"""Tests for role-based dependencies in app.api.dependencies.authentication."""

from unittest.mock import MagicMock

import pytest

from app.api.dependencies.authentication import get_current_role
from app.exceptions.base import AuthorizationError
from app.models.enums import Role

pytestmark = pytest.mark.unit


def _make_request_with_role(role: str | None):
    """Create a mock Request with `role` in state."""
    request = MagicMock()
    request.state.role = role
    return request


class TestGetCurrentRole:
    async def test_returns_role_enum_for_valid_role(self):
        request = _make_request_with_role("admin")
        result = await get_current_role(request)
        assert result == Role.ADMIN

    async def test_raises_authorization_error_when_no_role(self):
        request = _make_request_with_role(None)
        with pytest.raises(AuthorizationError, match="No role in token"):
            await get_current_role(request)

    async def test_raises_authorization_error_for_unknown_role(self):
        request = _make_request_with_role("unknown_role")
        with pytest.raises(AuthorizationError, match="Unknown role"):
            await get_current_role(request)
