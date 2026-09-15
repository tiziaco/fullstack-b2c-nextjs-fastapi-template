"""Agent dependencies for FastAPI dependency injection."""

from typing import Annotated

from fastapi import (
    Depends,
    Request,
)

from app.agents.chatbot.graph import ChatbotAgent


def get_chatbot_agent(request: Request) -> ChatbotAgent:
    """Get the chatbot agent from application state.

    Args:
        request: The FastAPI request object.

    Returns:
        ChatbotAgent: The initialized chatbot agent instance.

    Raises:
        RuntimeError: If agents not initialized in app state.
    """
    if not hasattr(request.app.state, "agents"):
        raise RuntimeError("Agents not initialized in application state")

    return request.app.state.agents["chatbot"]


# Type alias for dependency injection
ChatbotAgentDep = Annotated[ChatbotAgent, Depends(get_chatbot_agent)]


# Future agent dependencies can be added here:
# def get_support_agent(request: Request) -> SupportAgent:
#     return request.app.state.agents["support"]  # noqa: ERA001
#
# SupportAgentDep = Annotated[SupportAgent, Depends(get_support_agent)]  # noqa: ERA001
