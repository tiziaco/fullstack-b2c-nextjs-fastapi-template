"""Tests for app.agents.chatbot.graph — tool execution, logging and metrics."""

import pytest
from langchain_core.tools import tool
from prometheus_client import REGISTRY

from app.agents.chatbot.graph import (
    TOOL_ARGS_LOG_LIMIT,
    TOOL_FAILED_MESSAGE,
    TOOL_UNKNOWN_MESSAGE,
    ChatbotAgent,
    _format_tool_args,
)
from app.agents.chatbot.tools import tools

pytestmark = pytest.mark.unit


@tool
def ok_tool(text: str) -> str:
    """Return the input unchanged."""
    return f"result for {text}"


@tool
def exploding_tool(text: str) -> str:
    """Always fail."""
    raise RuntimeError("upstream is down")


def _tool_calls(tool_name: str) -> int:
    """The `error`-outcome count for a tool, or 0 before it has ever been seen.

    Read as a delta around the call under test: `app/core/metrics.py` registers
    on the default registry at import, so counters accumulate across every test
    in the process and an absolute assertion would depend on test order.
    """
    value = REGISTRY.get_sample_value("tool_calls_total", {"tool": tool_name, "outcome": "error"})
    return int(value or 0)


@pytest.fixture
def agent() -> ChatbotAgent:
    """A real ChatbotAgent.

    Constructible without a credential: `bind_tools` records the tools and
    leaves the client to be built on first use.
    """
    return ChatbotAgent()


class TestInvokeTool:
    """Tests for `_invoke_tool` — the unit that owns one tool call."""

    @pytest.mark.asyncio
    async def test_tool_result_is_returned_to_the_model(self, agent):
        agent.tools_by_name["ok_tool"] = ok_tool

        message = await agent._invoke_tool({"name": "ok_tool", "args": {"text": "hi"}, "id": "call_1"})

        assert message.content == "result for hi"
        assert message.status == "success"
        assert message.tool_call_id == "call_1"

    @pytest.mark.asyncio
    async def test_tool_failure_returns_an_error_message(self, agent):
        """A raising tool must not escape the node, and must be visibly an error.

        With `handle_tool_error=True` on the tool a failure came back as an
        ordinary success-status message carrying the exception text, so a search
        failing every time was indistinguishable from one working.
        """
        agent.tools_by_name["exploding_tool"] = exploding_tool
        before = _tool_calls("exploding_tool")

        message = await agent._invoke_tool({"name": "exploding_tool", "args": {"text": "hi"}, "id": "call_2"})

        assert message.status == "error"
        assert message.content == TOOL_FAILED_MESSAGE
        assert "upstream is down" not in message.content
        assert _tool_calls("exploding_tool") == before + 1

    @pytest.mark.asyncio
    async def test_unknown_tool_does_not_raise(self, agent):
        """A name the model invented used to raise KeyError out of the graph."""
        message = await agent._invoke_tool({"name": "no_such_tool", "args": {}, "id": "call_3"})

        assert message.status == "error"
        assert message.content == TOOL_UNKNOWN_MESSAGE
        assert REGISTRY.get_sample_value("tool_calls_total", {"tool": "no_such_tool", "outcome": "unknown_tool"})


class TestToolConfiguration:
    """Tests for the tools themselves, not the node."""

    @pytest.mark.parametrize("configured_tool", tools, ids=lambda t: t.name)
    def test_tools_do_not_swallow_their_own_errors(self, configured_tool):
        """No tool may set `handle_tool_error`.

        It makes LangChain catch the exception and return it as a plain string
        result, so `_invoke_tool`'s except branch never runs: the call is counted
        a success and the raw upstream error is handed to the model and persisted
        into the checkpoint. Every assertion about failure handling in this file
        is void for a tool that sets it, and nothing else would tell you.
        """
        assert not configured_tool.handle_tool_error


class TestFormatToolArgs:
    """Tests for the log rendering of tool arguments."""

    def test_short_args_are_rendered_whole(self):
        assert _format_tool_args({"query": "example query"}) == '{"query": "example query"}'

    def test_long_args_are_truncated(self):
        rendered = _format_tool_args({"query": "x" * 500})

        assert len(rendered) == TOOL_ARGS_LOG_LIMIT + 3
        assert rendered.endswith("...")
