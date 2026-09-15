"""Agents package for LangGraph-based AI agents.

This package contains the base agent abstraction, shared components,
and specific agent implementations.

Structure:
- base/: Abstract BaseAgent class
- shared/: Reusable components (memory, checkpointing, observability)
- chatbot/: Chatbot agent implementation
"""

from app.agents.base import BaseAgent
from app.agents.chatbot import ChatbotAgent

__all__ = [
    "BaseAgent",
    "ChatbotAgent",
]
