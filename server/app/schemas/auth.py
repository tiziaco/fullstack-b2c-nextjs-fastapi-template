"""Authentication and user schemas for the API."""

from datetime import datetime
from typing import Optional

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
)


class UserResponse(BaseModel):
    """Response model for user profile.

    Attributes:
        id: Internal user ID (UUID string)
        clerk_id: External Clerk user ID
        email: User's email address
        first_name: User's first name
        last_name: User's last name
        avatar_url: User's avatar URL
        created_at: When the user was created
    """

    id: str = Field(..., description="Internal user ID (UUID)")
    clerk_id: str = Field(..., description="Clerk user ID")
    email: EmailStr = Field(..., description="User's email address")
    first_name: Optional[str] = Field(None, description="User's first name")
    last_name: Optional[str] = Field(None, description="User's last name")
    avatar_url: Optional[str] = Field(None, description="User's avatar URL")
    created_at: datetime = Field(..., description="Account creation timestamp")

    model_config = {"from_attributes": True}
