"""Exception exports for the application.

This module provides a centralized location for importing all exception
classes and handlers used throughout the application.
"""

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
from app.exceptions.handlers import (
    global_exception_handler,
    service_exception_handler,
    validation_exception_handler,
)

__all__ = [
    # Base exceptions
    "ServiceError",
    "AuthenticationError",
    "AuthorizationError",
    "ConflictError",
    "DatabaseConflictError",
    "DatabaseConnectionError",
    "DatabaseError",
    "InvalidCredentialsError",
    "NotFoundError",
    "ValidationError",
    # Handlers
    "service_exception_handler",
    "validation_exception_handler",
    "global_exception_handler",
]
