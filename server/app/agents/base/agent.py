"""Base agent class for all LangGraph agents."""

import asyncio
from abc import (
    ABC,
    abstractmethod,
)
from typing import (
    AsyncGenerator,
    Optional,
)

from langchain_core.messages import (
    BaseMessage,
    convert_to_openai_messages,
)
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import StateSnapshot
from mem0 import AsyncMemory

from app.agents.shared.memory import (
    get_relevant_memory,
    update_memory,
)
from app.agents.shared.observability import create_graph_config
from app.core.logging import logger
from app.schemas import Message
from app.utils import dump_messages


class BaseAgent(ABC):
    """Abstract base class for all LangGraph agents.

    Provides response handling, streaming, chat history and memory management;
    subclasses implement create_graph() for their own workflow. The graph is
    compiled once at application startup, and every method here assumes it.
    """

    def __init__(self):
        self._graph: Optional[CompiledStateGraph] = None
        self.memory: Optional[AsyncMemory] = None

    @abstractmethod
    async def create_graph(self, checkpointer: AsyncPostgresSaver) -> CompiledStateGraph:
        """Create and compile this agent's workflow. Called once, at startup."""
        pass

    def is_ready(self) -> bool:
        """Whether the agent's graph has been compiled and is ready for use."""
        return self._graph is not None

    async def get_response(
        self,
        messages: list[Message],
        conversation_id: str,
        user_id: Optional[str] = None,
    ) -> list[dict]:
        """Get a response from the agent."""
        if not self.is_ready():
            raise RuntimeError(
                "Agent graph not initialized. This should not happen if startup completed successfully."
            )

        config = create_graph_config(conversation_id, user_id)

        relevant_memory = (await get_relevant_memory(user_id, messages[-1].content)) or "No relevant memory found."

        try:
            response = await self._graph.ainvoke(
                input={"messages": dump_messages(messages), "long_term_memory": relevant_memory},
                config=config,
            )
            # Backgrounded: the memory write must not delay the response.
            asyncio.create_task(
                update_memory(user_id, convert_to_openai_messages(response["messages"]), config["metadata"])
            )
            return self._process_messages(response["messages"])
        except Exception as e:
            logger.exception("error_getting_response", error=str(e), conversation_id=conversation_id)
            raise

    async def get_stream_response(
        self,
        messages: list[Message],
        conversation_id: str,
        user_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream the agent's response, token by token."""
        if not self.is_ready():
            raise RuntimeError(
                "Agent graph not initialized. This should not happen if startup completed successfully."
            )

        config = create_graph_config(conversation_id, user_id)

        relevant_memory = (await get_relevant_memory(user_id, messages[-1].content)) or "No relevant memory found."

        try:
            async for token, _ in self._graph.astream(
                {"messages": dump_messages(messages), "long_term_memory": relevant_memory},
                config=config,
                stream_mode="messages",
            ):
                try:
                    yield token.content
                except Exception as token_error:
                    logger.exception("error_processing_token", error=str(token_error), conversation_id=conversation_id)
                    continue  # one bad token must not end the stream

            state: StateSnapshot = await self._graph.aget_state(config=config)
            if state.values and "messages" in state.values:
                asyncio.create_task(
                    update_memory(user_id, convert_to_openai_messages(state.values["messages"]), config["metadata"])
                )
        except Exception as stream_error:
            logger.exception("error_in_stream_processing", error=str(stream_error), conversation_id=conversation_id)
            raise stream_error

    async def get_chat_history(self, conversation_id: str) -> list[Message]:
        """Get the chat history for a given conversation."""
        if not self.is_ready():
            raise RuntimeError(
                "Agent graph not initialized. This should not happen if startup completed successfully."
            )

        state: StateSnapshot = await self._graph.aget_state(config={"configurable": {"thread_id": conversation_id}})
        return self._process_messages(state.values["messages"]) if state.values else []

    def _process_messages(self, messages: list[BaseMessage]) -> list[Message]:
        """Convert LangChain messages to Message, keeping only user and assistant."""
        openai_style_messages = convert_to_openai_messages(messages)
        return [
            Message(role=message["role"], content=str(message["content"]))
            for message in openai_style_messages
            if message["role"] in ["assistant", "user"] and message["content"]
        ]

    def _get_last_response(self, messages: list[BaseMessage]) -> Message:
        """The last assistant message, or an empty one if there is none."""
        openai_style_messages = convert_to_openai_messages(messages)
        for message in reversed(openai_style_messages):
            if message["role"] == "assistant" and message["content"]:
                return Message(role="assistant", content=str(message["content"]))
        return Message(role="assistant", content="")
