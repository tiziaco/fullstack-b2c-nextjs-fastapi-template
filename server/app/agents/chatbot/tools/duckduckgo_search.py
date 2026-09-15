"""DuckDuckGo search tool for the chatbot agent.

This module provides a DuckDuckGo search tool that can be used with LangGraph
to perform web searches. It returns up to 10 search results.

Errors are deliberately left to propagate. `handle_tool_error` would make
LangChain catch them here and hand the exception text back as an ordinary
result, so a search failing every time would be counted a success, logged as
one, and its raw error string persisted into the conversation's checkpoint.
`ChatbotAgent._invoke_tool` owns failure instead — one place that also covers a
tool name the model invented, and that covers any tool added later without it
having to opt in.
"""

from langchain_community.tools import DuckDuckGoSearchResults

duckduckgo_search_tool = DuckDuckGoSearchResults(num_results=10)
