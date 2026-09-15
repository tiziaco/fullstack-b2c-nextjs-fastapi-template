"""Chatbot agent implementation using LangGraph."""

import json
import time
from typing import Optional

from langchain_core.messages import ToolMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import (
    END,
    StateGraph,
)
from langgraph.graph.state import (
    Command,
    CompiledStateGraph,
)
from langgraph.types import RunnableConfig

from app.agents.base import BaseAgent
from app.agents.chatbot.prompts import load_system_prompt
from app.agents.chatbot.state import GraphState
from app.agents.chatbot.tools import tools
from app.core.config import settings
from app.core.logging import logger
from app.core.metadata import PROJECT_NAME
from app.core.metrics import (
    llm_inference_duration_seconds,
    tool_call_duration_seconds,
    tool_calls_total,
)
from app.services.llm import llm_service
from app.utils import (
    dump_messages,
    prepare_messages,
    process_llm_response,
)

# What the model is told when a tool call does not produce a result. Fixed text
# rather than the exception: a tool result becomes a ToolMessage in graph state,
# which LangGraph persists to the checkpoint tables and which re-enters the
# model's context on every later turn of the conversation. Upstream error strings
# do not belong in either place.
TOOL_FAILED_MESSAGE = "The tool failed to run. Tell the user this information could not be retrieved right now."
TOOL_UNKNOWN_MESSAGE = "That tool does not exist. Answer without it."

# Tool arguments are logged, so they need a ceiling. For the search tool the
# argument is the query — the most useful field when diagnosing a bad answer —
# but a future tool taking a large payload would otherwise dump it into every
# line.
TOOL_ARGS_LOG_LIMIT = 200


def _format_tool_args(args: dict) -> str:
    """Render tool arguments as JSON, truncated past `TOOL_ARGS_LOG_LIMIT`."""
    rendered = json.dumps(args, default=str, ensure_ascii=False)
    if len(rendered) <= TOOL_ARGS_LOG_LIMIT:
        return rendered
    return rendered[:TOOL_ARGS_LOG_LIMIT] + "..."


class ChatbotAgent(BaseAgent):
    """A LangGraph conversational workflow with tools, memory and checkpointing."""

    def __init__(self):
        super().__init__()

        self.llm_service = llm_service
        self.llm_service.bind_tools(tools)
        self.tools_by_name = {tool.name: tool for tool in tools}

        logger.info(
            "chatbot_agent_initialized",
            model=settings.llm.DEFAULT_LLM_MODEL,
            environment=settings.ENVIRONMENT.value,
        )

    async def _chat(self, state: GraphState, config: RunnableConfig) -> Command:
        """Process the chat state and generate a response."""
        current_llm = self.llm_service.get_llm()
        model_name = self.llm_service.current_model_name()

        system_prompt = load_system_prompt(long_term_memory=state.long_term_memory)

        messages = prepare_messages(state.messages, current_llm, system_prompt)

        try:
            with llm_inference_duration_seconds.labels(model=model_name).time():
                response_message = await self.llm_service.call(dump_messages(messages))

            response_message = process_llm_response(response_message)

            logger.info(
                "llm_response_generated",
                conversation_id=config["configurable"]["thread_id"],
                model=model_name,
                environment=settings.ENVIRONMENT.value,
            )

            if response_message.tool_calls:
                goto = "tool_call"
            else:
                goto = END

            return Command(update={"messages": [response_message]}, goto=goto)
        except Exception as e:
            logger.exception(
                "llm_call_failed_all_models",
                conversation_id=config["configurable"]["thread_id"],
                error=str(e),
                environment=settings.ENVIRONMENT.value,
            )
            raise Exception(f"failed to get llm response after trying all models: {str(e)}")

    async def _invoke_tool(self, tool_call: dict) -> ToolMessage:
        """Run one tool call, recording what happened.

        This node hand-rolls the execution loop rather than using LangChain's
        prebuilt ToolNode, so error handling belongs here and not on the tools:
        one place covers a tool raising *and* a name the model invented, and
        every tool added later is covered without opting in. The returned
        ToolMessage carries `status="error"` if there was no result.
        """
        tool_name = tool_call["name"]
        tool = self.tools_by_name.get(tool_name)

        if tool is None:
            # A hallucinated name used to raise KeyError out of the graph and
            # surface as a bare 500 with nothing naming the tool.
            logger.error(
                "tool_call_unknown_tool",
                tool_name=tool_name,
                known_tools=sorted(self.tools_by_name),
            )
            tool_calls_total.labels(tool=tool_name, outcome="unknown_tool").inc()
            return ToolMessage(
                content=TOOL_UNKNOWN_MESSAGE,
                name=tool_name,
                tool_call_id=tool_call["id"],
                status="error",
            )

        logger.debug("tool_call_started", tool_name=tool_name, tool_args=_format_tool_args(tool_call["args"]))
        started = time.perf_counter()

        try:
            tool_result = await tool.ainvoke(tool_call["args"])
        except Exception as e:
            # Timed even on failure: a tool that fails slowly is a different
            # problem from one that fails fast.
            duration = time.perf_counter() - started
            tool_call_duration_seconds.labels(tool=tool_name).observe(duration)
            tool_calls_total.labels(tool=tool_name, outcome="error").inc()
            logger.exception(
                "tool_call_failed",
                tool_name=tool_name,
                tool_args=_format_tool_args(tool_call["args"]),
                duration_ms=round(duration * 1000),
                error=str(e),
            )
            return ToolMessage(
                content=TOOL_FAILED_MESSAGE,
                name=tool_name,
                tool_call_id=tool_call["id"],
                status="error",
            )

        duration = time.perf_counter() - started
        tool_call_duration_seconds.labels(tool=tool_name).observe(duration)
        tool_calls_total.labels(tool=tool_name, outcome="success").inc()
        logger.info(
            "tool_call_completed",
            tool_name=tool_name,
            tool_args=_format_tool_args(tool_call["args"]),
            duration_ms=round(duration * 1000),
            result_chars=len(str(tool_result)),
        )
        return ToolMessage(
            content=tool_result,
            name=tool_name,
            tool_call_id=tool_call["id"],
        )

    async def _tool_call(self, state: GraphState) -> Command:
        """Run every tool call on the last message, then route back to chat."""
        outputs = [await self._invoke_tool(tool_call) for tool_call in state.messages[-1].tool_calls]
        return Command(update={"messages": outputs}, goto="chat")

    async def create_graph(self, checkpointer: AsyncPostgresSaver) -> CompiledStateGraph:
        """Create and compile the chatbot LangGraph workflow."""
        try:
            graph_builder = StateGraph(GraphState)
            graph_builder.add_node("chat", self._chat, ends=["tool_call", END])
            graph_builder.add_node("tool_call", self._tool_call, ends=["chat"])
            graph_builder.set_entry_point("chat")
            graph_builder.set_finish_point("chat")

            self._graph = graph_builder.compile(
                checkpointer=checkpointer,
                name=f"{PROJECT_NAME} Agent ({settings.ENVIRONMENT.value})",
            )

            logger.info(
                "graph_created",
                graph_name=f"{PROJECT_NAME} Agent",
                environment=settings.ENVIRONMENT.value,
                has_checkpointer=checkpointer is not None,
            )
        except Exception as e:
            logger.exception("graph_creation_failed", error=str(e), environment=settings.ENVIRONMENT.value)
            raise

        return self._graph
