"""Conversation CRUD endpoints for the authenticated user."""

import uuid
from typing import List

from fastapi import (
    APIRouter,
    Form,
    Request,
)

from app.agents.shared.checkpointing import delete_conversation_checkpoints
from app.api.dependencies.authentication import CurrentUser
from app.api.dependencies.conversation import UserConversation
from app.api.dependencies.database import DbSession
from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import logger
from app.schemas.conversation import ConversationResponse
from app.services.conversation import conversation_service
from app.utils.sanitization import sanitize_string

router = APIRouter()


@router.post(
    "/conversation",
    operation_id="createConversation",
    response_model=ConversationResponse,
    summary="Create a new chat conversation",
    description="Initialize a new chat conversation for the authenticated user with a unique conversation ID.",
)
@limiter.limit(settings.rate_limits.endpoints.CHAT[0])
async def create_conversation(request: Request, db_session: DbSession, user: CurrentUser):
    """Create a new chat conversation for the authenticated user."""
    conversation_id = str(uuid.uuid4())
    conversation = await conversation_service.create_conversation(db_session, conversation_id, user.id)

    logger.info(
        "conversation_created",
        conversation_id=conversation_id,
        user_id=user.id,
        name=conversation.name,
    )

    return ConversationResponse(
        conversation_id=conversation_id,
        name=conversation.name,
        created_at=conversation.created_at,
    )


@router.patch(
    "/conversation/{conversation_id}/name",
    operation_id="renameConversation",
    response_model=ConversationResponse,
    summary="Rename a chat conversation",
    description="Update the display name of an existing chat conversation.",
)
@limiter.limit(settings.rate_limits.endpoints.CHAT[0])
async def update_conversation_name(
    request: Request,
    conversation: UserConversation,
    db_session: DbSession,
    name: str = Form(...),
):
    """Update a conversation's name."""
    sanitized_name = sanitize_string(name)
    conversation = await conversation_service.update_conversation_name(db_session, conversation.id, sanitized_name)

    return ConversationResponse(
        conversation_id=conversation.id,
        name=conversation.name,
        created_at=conversation.created_at,
    )


@router.delete(
    "/conversation/{conversation_id}",
    operation_id="deleteConversation",
    status_code=204,
    summary="Delete a chat conversation",
    description="Remove a chat conversation and permanently delete all associated messages.",
)
@limiter.limit(settings.rate_limits.endpoints.CHAT[0])
async def delete_conversation(
    request: Request,
    conversation: UserConversation,
    db_session: DbSession,
    user: CurrentUser,
):
    """Delete a conversation for the authenticated user.

    Checkpoint data (the messages) is hard-deleted first; the conversation row
    is then soft-deleted.
    """
    await delete_conversation_checkpoints(conversation.id)
    await conversation_service.soft_delete_conversation(db_session, conversation.id)

    logger.info("conversation_deleted", conversation_id=conversation.id, user_id=user.id)


@router.get(
    "/conversations",
    operation_id="listConversations",
    response_model=List[ConversationResponse],
    summary="List all user chat conversations",
    description="Retrieve all chat conversations created by the authenticated user.",
)
@limiter.limit(settings.rate_limits.endpoints.CHAT[0])
async def get_user_conversations(request: Request, db_session: DbSession, user: CurrentUser):
    """Get all conversations for the authenticated user."""
    conversations = await conversation_service.get_user_conversations(db_session, user.id)
    return [
        ConversationResponse(
            conversation_id=sanitize_string(conversation.id),
            name=sanitize_string(conversation.name),
            created_at=conversation.created_at,
        )
        for conversation in conversations
    ]
