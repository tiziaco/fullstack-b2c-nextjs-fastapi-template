"""Prompts for the chatbot agent."""

import os
from datetime import datetime

from app.core.metadata import PROJECT_NAME


def load_system_prompt(**kwargs):
    """Load the system prompt from the file.

    Args:
        **kwargs: Additional template variables to format into the prompt.

    Returns:
        Formatted system prompt string.
    """
    with open(os.path.join(os.path.dirname(__file__), "system.md"), "r") as f:
        return f.read().format(
            agent_name=PROJECT_NAME + " Agent",
            current_date_and_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            **kwargs,
        )
