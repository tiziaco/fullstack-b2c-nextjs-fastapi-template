"""Tests for app.core.config — environment resolution and settings properties."""

import pytest

from app.core.config import AuthSettings, Environment, get_environment

pytestmark = pytest.mark.unit


class TestGetEnvironment:
    """Tests for get_environment() function."""

    @pytest.mark.parametrize(
        "env_value,expected",
        [
            ("production", Environment.PRODUCTION),
            ("prod", Environment.PRODUCTION),
            ("staging", Environment.STAGING),
            ("stage", Environment.STAGING),
            ("test", Environment.TEST),
            ("development", Environment.DEVELOPMENT),
            ("dev", Environment.DEVELOPMENT),  # falls to default case
            ("unknown", Environment.DEVELOPMENT),
            ("PRODUCTION", Environment.PRODUCTION),  # case insensitive
            ("Test", Environment.TEST),
        ],
        ids=[
            "production",
            "prod",
            "staging",
            "stage",
            "test",
            "development",
            "dev-fallback",
            "unknown-fallback",
            "uppercase",
            "mixed-case",
        ],
    )
    def test_environment_resolution(self, monkeypatch, env_value, expected):
        monkeypatch.setenv("APP_ENV", env_value)
        assert get_environment() == expected

    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("APP_ENV", raising=False)
        assert get_environment() == Environment.DEVELOPMENT


class TestAuthSettings:
    """Tests for AuthSettings derived properties."""

    def test_jwks_url_derived_from_issuer(self):
        auth = AuthSettings(ISSUER="https://clerk.example.com")
        assert auth.jwks_url == "https://clerk.example.com/.well-known/jwks.json"

    def test_jwks_url_empty_issuer(self):
        auth = AuthSettings(ISSUER="")
        assert auth.jwks_url == "/.well-known/jwks.json"


class TestEnvironmentEnum:
    """Tests for Environment enum values."""

    def test_enum_values(self):
        assert Environment.DEVELOPMENT.value == "development"
        assert Environment.STAGING.value == "staging"
        assert Environment.PRODUCTION.value == "production"
        assert Environment.TEST.value == "test"

    def test_enum_is_string(self):
        assert isinstance(Environment.PRODUCTION, str)
        assert Environment.PRODUCTION == "production"
