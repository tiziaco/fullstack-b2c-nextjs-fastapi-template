"""Agent factory for initializing and managing multiple LangGraph agents.

This module provides a registry pattern for agents, allowing easy addition
of new agent types without modifying core initialization logic.
"""

from typing import (
    Dict,
    Type,
)

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.agents.base.agent import BaseAgent
from app.agents.chatbot.graph import ChatbotAgent
from app.core.logging import logger

# Agent Registry - Add new agents here
AGENT_REGISTRY: Dict[str, Type[BaseAgent]] = {
    "chatbot": ChatbotAgent,
    # Future agents can be added here:
    # "support": SupportAgent,  # noqa: ERA001
    # "analyst": AnalystAgent,  # noqa: ERA001
}


async def initialize_agents(checkpointer: AsyncPostgresSaver) -> Dict[str, BaseAgent]:
    """Initialize all registered agents with pre-compiled graphs.

    This function:
    1. Iterates through the agent registry
    2. Instantiates each agent class
    3. Pre-compiles the graph with the provided checkpointer
    4. Logs initialization status for each agent
    5. Returns a dictionary of ready-to-use agent instances

    Args:
        checkpointer: The AsyncPostgresSaver instance for all agents to share

    Returns:
        Dict[str, BaseAgent]: Dictionary mapping agent names to initialized instances

    Raises:
        Exception: If any agent fails to initialize (fails fast for startup safety)
    """
    agents: Dict[str, BaseAgent] = {}

    for agent_name, agent_class in AGENT_REGISTRY.items():
        logger.info(
            "agent_initialization_started",
            agent_name=agent_name,
            agent_class=agent_class.__name__,
        )

        # Instantiate the agent
        agent = agent_class()

        # Pre-compile the graph at startup
        await agent.create_graph(checkpointer)

        # Verify graph is ready
        if not agent.is_ready():
            raise Exception(f"Agent {agent_name} failed to initialize - graph not compiled")

        agents[agent_name] = agent

        logger.info(
            "agent_initialized",
            agent_name=agent_name,
            graph_compiled=True,
        )

    logger.info(
        "all_agents_initialized",
        agent_count=len(agents),
        agent_names=list(agents.keys()),
    )

    return agents
