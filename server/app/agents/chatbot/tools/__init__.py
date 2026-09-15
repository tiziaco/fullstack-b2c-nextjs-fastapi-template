"""Tools for the chatbot agent.

This package contains tools that can be used with the chatbot agent
to extend its capabilities with web search and other external integrations.
"""

from langchain_core.tools.base import BaseTool

from app.agents.chatbot.tools.duckduckgo_search import duckduckgo_search_tool

tools: list[BaseTool] = [duckduckgo_search_tool]

__all__ = ["tools", "duckduckgo_search_tool"]
