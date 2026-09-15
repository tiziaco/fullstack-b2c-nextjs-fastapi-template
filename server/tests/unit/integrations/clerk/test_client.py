"""Tests for app.integrations.clerk.client — Clerk API error mapping and email extraction."""

from unittest.mock import MagicMock

import httpx
import pytest
from clerk_backend_api import Clerk
from clerk_backend_api.models import SDKError

from app.integrations.clerk.client import ClerkClient
from app.integrations.clerk.exceptions import (
    ClerkAPIError,
    ClerkAuthenticationError,
    ClerkRateLimitError,
    ClerkUserNotFoundError,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def service():
    """Fresh ClerkClient with mocked client."""
    svc = ClerkClient()
    svc._client = MagicMock()
    return svc


def _client_returning(status: int, body: dict | None = None) -> ClerkClient:
    """A ClerkClient wrapping a real SDK whose transport answers with `status`.

    The routing under test is the SDK's, not ours: which exception class a given
    status produces is decided by the generated `match_response` ladder in
    clerk_backend_api/users.py, and it differs per operation — `users.get` sends
    400/401/404 to ClerkErrors, and everything else becomes SDKError.

    This file used to fabricate a ClerkErrors carrying the status it wanted,
    which asserts our mapping against an object the SDK would never raise. Four
    unreachable branches survived here that way.

    Never pass a 5XX. The SDK's default RetryConfig retries those with backoff
    for up to an hour (users.py:948), which would hang the suite; 4XX is not
    retried and returns immediately. Use `_sdk_error` for those instead.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body if body is not None else {"errors": []})

    svc = ClerkClient()
    svc._client = Clerk(
        bearer_auth="sk_test_not_a_real_key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    return svc


def _sdk_error(status: int) -> SDKError:
    """A genuine SDKError, for the statuses a MockTransport must not serve."""
    request = httpx.Request("GET", "https://api.clerk.com/v1/users/user_123")
    response = httpx.Response(status, json={"errors": []}, request=request)
    return SDKError("API error occurred", response, response.text)


class TestGetUser:
    """Tests for ClerkClient.get_user()."""

    def test_success(self, service):
        mock_user = MagicMock()
        service._client.users.get.return_value = mock_user

        result = service.get_user("user_123")

        assert result == mock_user
        service._client.users.get.assert_called_once_with(user_id="user_123")

    def test_404_raises_not_found(self):
        with pytest.raises(ClerkUserNotFoundError):
            _client_returning(404).get_user("user_missing")

    def test_401_raises_authentication_error(self):
        with pytest.raises(ClerkAuthenticationError):
            _client_returning(401).get_user("user_123")

    def test_429_raises_rate_limit_error(self):
        """A throttled read must surface as ClerkRateLimitError.

        `users.get` routes only 400/401/404 to ClerkErrors, so a 429 arrives as
        SDKError. Catching only ClerkErrors let it fall through to the bare
        `except Exception`, which logged a full traceback and raised
        ClerkAPIError — a 502 — for an ordinary upstream condition.
        """
        with pytest.raises(ClerkRateLimitError):
            _client_returning(429).get_user("user_123")

    def test_500_raises_generic_api_error(self, service):
        service._client.users.get.side_effect = _sdk_error(500)

        with pytest.raises(ClerkAPIError):
            service.get_user("user_123")

    def test_unexpected_exception_raises_api_error(self, service):
        service._client.users.get.side_effect = RuntimeError("network down")

        with pytest.raises(ClerkAPIError, match="Unexpected error"):
            service.get_user("user_123")


class TestDeleteUser:
    """Tests for ClerkClient.delete_user()."""

    def test_success(self, service):
        service.delete_user("user_123")

        service._client.users.delete.assert_called_once_with(user_id="user_123")

    def test_404_is_not_an_error(self):
        """Already gone is the outcome the caller asked for."""
        assert _client_returning(404).delete_user("user_missing") is None

    def test_401_raises_authentication_error(self):
        with pytest.raises(ClerkAuthenticationError):
            _client_returning(401).delete_user("user_123")

    def test_429_raises_rate_limit_error(self):
        with pytest.raises(ClerkRateLimitError):
            _client_returning(429).delete_user("user_123")

    def test_unexpected_exception_raises_api_error(self, service):
        service._client.users.delete.side_effect = RuntimeError("network down")

        with pytest.raises(ClerkAPIError, match="Unexpected error"):
            service.delete_user("user_123")


class TestGetPrimaryEmail:
    """Tests for ClerkClient.get_primary_email()."""

    def test_primary_email_found(self, service):
        email_obj = MagicMock()
        email_obj.id = "email_primary"
        email_obj.email_address = "primary@example.com"

        clerk_user = MagicMock()
        clerk_user.email_addresses = [email_obj]
        clerk_user.primary_email_address_id = "email_primary"

        assert service.get_primary_email(clerk_user) == "primary@example.com"

    def test_fallback_to_first_email(self, service):
        primary = MagicMock()
        primary.id = "email_primary"
        primary.email_address = "primary@example.com"

        other = MagicMock()
        other.id = "email_other"
        other.email_address = "other@example.com"

        clerk_user = MagicMock()
        clerk_user.email_addresses = [other, primary]
        clerk_user.primary_email_address_id = "email_nonexistent"

        assert service.get_primary_email(clerk_user) == "other@example.com"

    def test_no_emails_returns_none(self, service):
        clerk_user = MagicMock()
        clerk_user.email_addresses = []

        assert service.get_primary_email(clerk_user) is None
