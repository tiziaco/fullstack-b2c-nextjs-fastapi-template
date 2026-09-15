"""Tests for app.exceptions.base — exception hierarchy, status codes, error codes."""

import pytest

from app.exceptions.base import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    DatabaseConflictError,
    DatabaseConnectionError,
    DatabaseError,
    InvalidCredentialsError,
    NotFoundError,
    ServiceError,
    ValidationError,
)

pytestmark = pytest.mark.unit


class TestServiceError:
    """Tests for the base ServiceError class."""

    def test_default_status_code(self):
        err = ServiceError("something broke")
        assert err.status_code == 500

    def test_default_error_code(self):
        err = ServiceError("something broke")
        assert err.error_code == "INTERNAL_ERROR"

    def test_message_stored(self):
        err = ServiceError("something broke")
        assert err.message == "something broke"
        assert str(err) == "something broke"

    def test_context_kwargs_stored(self):
        err = ServiceError("fail", user_id="abc", attempt=3)
        assert err.context == {"user_id": "abc", "attempt": 3}

    def test_empty_context_when_no_kwargs(self):
        err = ServiceError("fail")
        assert err.context == {}


class TestAuthErrors:
    """Tests for authentication/authorization exceptions."""

    def test_authentication_error(self):
        err = AuthenticationError("not authenticated")
        assert err.status_code == 401
        assert err.error_code == "AUTHENTICATION_ERROR"

    def test_authorization_error(self):
        err = AuthorizationError("forbidden")
        assert err.status_code == 403
        assert err.error_code == "AUTHORIZATION_ERROR"

    def test_invalid_credentials_inherits_401(self):
        err = InvalidCredentialsError("bad creds")
        assert err.status_code == 401
        assert err.error_code == "INVALID_CREDENTIALS"
        assert isinstance(err, AuthenticationError)


class TestResourceErrors:
    """Tests for resource-related exceptions."""

    def test_validation_error(self):
        err = ValidationError("invalid input", field="email")
        assert err.status_code == 422
        assert err.error_code == "VALIDATION_ERROR"
        assert err.context == {"field": "email"}

    def test_not_found_error(self):
        err = NotFoundError("not found")
        assert err.status_code == 404
        assert err.error_code == "NOT_FOUND"

    def test_conflict_error(self):
        err = ConflictError("already exists")
        assert err.status_code == 409
        assert err.error_code == "CONFLICT"


class TestDatabaseErrors:
    """Tests for database exceptions."""

    def test_database_error(self):
        err = DatabaseError("db fail")
        assert err.status_code == 500
        assert err.error_code == "DATABASE_ERROR"

    def test_database_connection_error(self):
        err = DatabaseConnectionError("can't connect")
        assert err.status_code == 503
        assert err.error_code == "DATABASE_CONNECTION_ERROR"
        assert isinstance(err, DatabaseError)

    def test_database_conflict_error(self):
        err = DatabaseConflictError("unique violation")
        assert err.status_code == 409
        assert err.error_code == "DATABASE_CONFLICT"
        assert isinstance(err, DatabaseError)


class TestServiceExceptionHierarchy:
    """Tests that all exceptions inherit from ServiceError."""

    @pytest.mark.parametrize(
        "exc_class",
        [
            AuthenticationError,
            AuthorizationError,
            InvalidCredentialsError,
            ValidationError,
            NotFoundError,
            ConflictError,
            DatabaseError,
            DatabaseConnectionError,
            DatabaseConflictError,
        ],
        ids=lambda c: c.__name__,
    )
    def test_all_inherit_from_service_error(self, exc_class):
        assert issubclass(exc_class, ServiceError)
