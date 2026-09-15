"""User service domain exceptions."""

from app.exceptions.base import (
    ConflictError,
    NotFoundError,
)


class UserServiceError(Exception):
    """Base exception for user service errors."""

    pass


class UserNotFoundError(NotFoundError):
    """Exception raised when a user is not found."""

    error_code = "USER_NOT_FOUND"


class UserAlreadyExistsError(ConflictError):
    """Exception raised when attempting to create a user that already exists."""

    error_code = "USER_ALREADY_EXISTS"
