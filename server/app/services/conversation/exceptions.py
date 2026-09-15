"""Conversation service domain exceptions."""

from app.exceptions.base import (
    AuthorizationError,
    NotFoundError,
)


class ConversationServiceError(Exception):
    """Base exception for conversation service errors."""

    pass


class ConversationNotFoundError(NotFoundError):
    """Exception raised when a conversation is not found."""

    error_code = "CONVERSATION_NOT_FOUND"


class ConversationAccessDeniedError(AuthorizationError):
    """Exception raised when user attempts to access a conversation they don't own."""

    error_code = "CONVERSATION_ACCESS_DENIED"
