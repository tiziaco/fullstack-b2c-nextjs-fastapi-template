"""Tests for app.models.enums."""

import pytest

from app.models.enums import Role

pytestmark = pytest.mark.unit


class TestRole:
    def test_all_roles_defined(self):
        assert Role.USER == "user"
        assert Role.ADMIN == "admin"

    def test_role_from_string(self):
        assert Role("admin") == Role.ADMIN

    def test_role_invalid_string_raises(self):
        with pytest.raises(ValueError):
            Role("superadmin")

    def test_role_is_str(self):
        assert isinstance(Role.ADMIN, str)
