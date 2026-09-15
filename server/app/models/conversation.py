"""This file contains the conversation model for the application."""

from typing import (
    TYPE_CHECKING,
    List,
)

from sqlmodel import (
    Field,
    Relationship,
)

from app.models.base import (
    BaseModel,
    SoftDeleteMixin,
)

if TYPE_CHECKING:
    from app.models.user import User


class Conversation(BaseModel, SoftDeleteMixin, table=True):
    """Conversation model for storing chat conversations.

    GDPR Note:
    - This model uses soft delete (not anonymization) because:
      1. It doesn't contain personal data (just metadata: ID, user_id, name)
      2. Actual messages are in LangGraph checkpointing (separate storage)
      3. We can keep business records for analytics (non-personal)

    - When user requests deletion:
      1. Hard delete all message data from LangGraph checkpointing
      2. Soft delete these conversation records
      3. Anonymize the User record

    - The user_id foreign key remains valid after User anonymization
      (FK points to anonymized User record)

    Attributes:
        id: The primary key (conversation ID used in LangGraph)
        user_id: Foreign key to the user (remains valid after anonymization)
        name: Name of the conversation — cleared on user deletion (may contain PII)
        created_at: When the conversation was created (from BaseModel)
        updated_at: Last time the conversation was updated (auto-managed by BaseModel)
        deleted_at: When the conversation was soft deleted (from SoftDeleteMixin)
        user: Relationship to the conversation owner
    """

    id: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)  # Index for JOIN queries
    name: str = Field(default="")
    user: "User" = Relationship(back_populates="conversations")
