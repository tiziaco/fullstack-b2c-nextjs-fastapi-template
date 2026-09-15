"""Base exception classes for domain-specific errors.

This module defines the exception hierarchy for the application.
All custom exceptions should inherit from ServiceError.
"""

from typing import (
    Any,
    Dict,
    Optional,
)


class ServiceError(Exception):
    """Base exception for all service-level business logic errors.

    Attributes:
        message: Human-readable error message
        status_code: HTTP status code for the error
        error_code: Machine-readable error code for API clients
        context: Additional context data for logging and debugging
    """

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, **context: Any):
        """Initialize a service error.

        Args:
            message: Human-readable error description
            **context: Additional context as keyword arguments (for logging)
        """
        self.message = message
        self.context = context
        super().__init__(self.message)


# ============================================================================
# Authentication & Authorization Errors
# ============================================================================


class AuthenticationError(ServiceError):
    """Base exception for authentication failures."""

    status_code = 401
    error_code = "AUTHENTICATION_ERROR"


class AuthorizationError(ServiceError):
    """Base exception for authorization/permission failures."""

    status_code = 403
    error_code = "AUTHORIZATION_ERROR"


class InvalidCredentialsError(AuthenticationError):
    """Exception raised when user credentials are invalid."""

    error_code = "INVALID_CREDENTIALS"


# ============================================================================
# Validation Errors
# ============================================================================


class ValidationError(ServiceError):
    """Base exception for input validation failures."""

    status_code = 422
    error_code = "VALIDATION_ERROR"


# ============================================================================
# Resource Errors
# ============================================================================


class NotFoundError(ServiceError):
    """Base exception for resource not found errors."""

    status_code = 404
    error_code = "NOT_FOUND"


class ConflictError(ServiceError):
    """Base exception for resource conflict errors."""

    status_code = 409
    error_code = "CONFLICT"


# ============================================================================
# Database Errors
# ============================================================================


class DatabaseError(ServiceError):
    """Base exception for database-related errors."""

    status_code = 500
    error_code = "DATABASE_ERROR"


class DatabaseConnectionError(DatabaseError):
    """Exception raised when database connection fails."""

    status_code = 503
    error_code = "DATABASE_CONNECTION_ERROR"


class DatabaseConflictError(DatabaseError):
    """Exception raised for database constraint violations."""

    status_code = 409
    error_code = "DATABASE_CONFLICT"
