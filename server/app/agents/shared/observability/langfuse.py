"""Langfuse observability utilities for agents."""

from typing import Optional

from langfuse.langchain import CallbackHandler

from app.core.config import settings


def create_graph_config(
    conversation_id: str,
    user_id: Optional[str] = None,
) -> dict:
    """Create a standard graph configuration dictionary.

    Args:
        conversation_id: The conversation/thread ID.
        user_id: Optional user ID for tracking.

    Returns:
        Configuration dictionary with callbacks and metadata.
    """
    return {
        "configurable": {"thread_id": conversation_id},
        "callbacks": [CallbackHandler()],
        "metadata": {
            # Standard metadata
            "user_id": user_id,
            "conversation_id": conversation_id,
            "environment": settings.ENVIRONMENT.value,
            "debug": settings.DEBUG,
            # Langfuse-specific metadata keys (v3 approach)
            "langfuse_user_id": user_id,
            "langfuse_session_id": conversation_id,
            "langfuse_tags": [settings.ENVIRONMENT.value],
        },
    }
