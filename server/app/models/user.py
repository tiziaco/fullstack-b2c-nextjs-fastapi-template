"""This file contains the user model for the application."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime
from sqlmodel import Field, Relationship

from app.models.base import AnonymizableMixin, BaseModel

if TYPE_CHECKING:
    from app.models.conversation import Conversation


class User(BaseModel, AnonymizableMixin, table=True):
    """User model for storing user accounts.

    GDPR Compliance:
    - When user requests deletion, use anonymize_user() to clear personal data
    - Keep the record ID for referential integrity (conversations, etc.)
    - Mark with anonymized_at timestamp

    Attributes:
        id: Internal UUID primary key for DB relationships
        clerk_id: External Clerk user ID for auth lookups (anonymized on deletion)
        email: User's email address (anonymized on deletion)
        email_verified: Whether the email is verified in Clerk
        first_name: User's first name from Clerk (anonymized on deletion)
        last_name: User's last name from Clerk (anonymized on deletion)
        avatar_url: User's avatar URL from Clerk (anonymized on deletion)
        last_synced_at: Last time data was synced from Clerk
        created_at: When the user was created (from BaseModel)
        updated_at: Last time the record was updated (auto-managed by BaseModel)
        anonymized_at: When personal data was anonymized (GDPR deletion)
        conversations: Relationship to user's chat conversations
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    clerk_id: str = Field(unique=True, index=True)
    email: str = Field(unique=True, index=True)
    email_verified: bool = Field(default=False)
    first_name: Optional[str] = Field(default=None)
    last_name: Optional[str] = Field(default=None)
    avatar_url: Optional[str] = Field(default=None)
    last_synced_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
    )
    conversations: List["Conversation"] = Relationship(back_populates="user")

    def anonymize_user(self) -> None:
        """Anonymize user personal data for GDPR compliance."""
        anonymous_id = f"deleted_user_{self.id[:8]}"
        self.clerk_id = anonymous_id
        self.email = f"{anonymous_id}@anonymized.local"
        self.email_verified = False
        self.first_name = None
        self.last_name = None
        self.avatar_url = None

        for conversation in self.conversations:
            conversation.name = ""

        self.mark_anonymized()


# Avoid circular imports
from app.models.conversation import Conversation  # noqa: E402
