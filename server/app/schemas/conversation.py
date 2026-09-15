"""This file contains the conversation schema for the chat agent."""

import re
from datetime import datetime

from pydantic import (
    BaseModel,
    Field,
    field_validator,
)


class ConversationResponse(BaseModel):
    """Response model for conversation operations.

    Attributes:
        conversation_id: The unique identifier for the chat conversation
        name: Name of the conversation (defaults to empty string)
        created_at: When the conversation was created
    """

    conversation_id: str = Field(..., description="The unique identifier for the chat conversation")
    name: str = Field(default="", description="Name of the conversation", max_length=100)
    created_at: datetime = Field(..., description="When the conversation was created")

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        """Sanitize the conversation name.

        Args:
            v: The name to sanitize

        Returns:
            str: The sanitized name
        """
        # Remove any potentially harmful characters
        sanitized = re.sub(r'[<>{}[\]()\'"`]', "", v)
        return sanitized
