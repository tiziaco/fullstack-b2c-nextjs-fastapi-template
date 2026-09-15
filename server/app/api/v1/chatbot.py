"""Chatbot API endpoints for handling chat interactions."""

import json

from fastapi import (
    APIRouter,
    Request,
)
from fastapi.responses import StreamingResponse

from app.agents.shared.checkpointing import delete_conversation_checkpoints
from app.api.dependencies.agent import ChatbotAgentDep
from app.api.dependencies.authentication import CurrentUser
from app.api.dependencies.conversation import UserConversation
from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import logger
from app.core.metrics import llm_stream_duration_seconds
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationHistory,
    Message,
    StreamResponse,
)

router = APIRouter()


@router.post(
    "/chat/{conversation_id}",
    operation_id="sendChatMessage",
    response_model=ChatResponse,
    summary="Send a message and get a response",
    description="Process a chat message and return the AI agent's response.",
)
@limiter.limit(settings.rate_limits.endpoints.CHAT[0])
async def chat(
    conversation: UserConversation,
    request: Request,
    chat_request: ChatRequest,
    user: CurrentUser,
    agent: ChatbotAgentDep,
):
    """Process a chat request using LangGraph."""
    logger.info(
        "chat_request_received",
        conversation_id=conversation.id,
        message_length=len(chat_request.message),
    )

    user_message = Message(role="user", content=chat_request.message)
    result = await agent.get_response([user_message], conversation.id, user_id=user.id)

    logger.info("chat_request_processed", conversation_id=conversation.id)

    return ChatResponse(message=result[-1])


@router.post(
    "/chat/{conversation_id}/stream",
    operation_id="streamChatMessage",
    tags=["streaming"],
    summary="Stream chat response in real-time",
    description="Send a message and receive the AI agent's response as a server-sent event stream.",
)
@limiter.limit(settings.rate_limits.endpoints.CHAT_STREAM[0])
async def chat_stream(
    conversation: UserConversation,
    request: Request,
    chat_request: ChatRequest,
    user: CurrentUser,
    agent: ChatbotAgentDep,
):
    """Process a chat request using LangGraph, streaming the response."""
    logger.info(
        "stream_chat_request_received",
        conversation_id=conversation.id,
        message_length=len(chat_request.message),
    )

    async def event_generator():
        """Yield the response as server-sent events, one JSON payload per chunk."""
        try:
            full_response = ""
            user_message = Message(role="user", content=chat_request.message)
            with llm_stream_duration_seconds.labels(model=agent.llm_service.current_model_name()).time():
                async for chunk in agent.get_stream_response([user_message], conversation.id, user_id=user.id):
                    full_response += chunk
                    response = StreamResponse(content=chunk, done=False)
                    yield f"data: {json.dumps(response.model_dump())}\n\n"

            final_response = StreamResponse(content="", done=True)
            yield f"data: {json.dumps(final_response.model_dump())}\n\n"

        except Exception as e:
            logger.error(
                "stream_chat_request_failed",
                conversation_id=conversation.id,
                error=str(e),
                exc_info=True,
            )
            error_response = StreamResponse(content="An error occurred. Please try again.", done=True)
            yield f"data: {json.dumps(error_response.model_dump())}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get(
    "/chat/{conversation_id}/messages",
    operation_id="listChatMessages",
    response_model=ConversationHistory,
    summary="Get conversation chat history",
    description="Retrieve all messages from the specified chat conversation.",
)
@limiter.limit(settings.rate_limits.endpoints.MESSAGES[0])
async def get_conversation_messages(
    conversation: UserConversation,
    request: Request,
    agent: ChatbotAgentDep,
):
    """Get all messages for a conversation."""
    messages = await agent.get_chat_history(conversation.id)
    return ConversationHistory(messages=messages)


@router.delete(
    "/chat/{conversation_id}/messages",
    operation_id="clearChatHistory",
    status_code=204,
    summary="Clear chat history",
    description="Remove all messages from the specified chat conversation.",
)
@limiter.limit(settings.rate_limits.endpoints.MESSAGES[0])
async def clear_chat_history(
    conversation: UserConversation,
    request: Request,
):
    """Clear all messages for a conversation."""
    await delete_conversation_checkpoints(conversation.id)
