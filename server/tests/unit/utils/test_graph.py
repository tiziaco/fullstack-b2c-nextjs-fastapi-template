"""Tests for app.utils.graph — message dumping, LLM response processing, message preparation."""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from app.schemas.chat import Message
from app.utils.graph import dump_messages, process_llm_response

pytestmark = pytest.mark.unit


class TestDumpMessages:
    """Tests for dump_messages()."""

    def test_converts_messages_to_dicts(self):
        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there"),
        ]
        result = dump_messages(messages)

        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "Hello"
        assert result[1]["role"] == "assistant"

    def test_empty_list(self):
        assert dump_messages([]) == []

    def test_single_message(self):
        result = dump_messages([Message(role="system", content="Be helpful")])
        assert len(result) == 1
        assert result[0]["role"] == "system"


class TestProcessLlmResponse:
    """Tests for process_llm_response()."""

    def test_string_content_passthrough(self):
        response = AIMessage(content="Hello world")
        result = process_llm_response(response)
        assert result.content == "Hello world"

    def test_list_with_text_blocks(self):
        response = AIMessage(
            content=[
                {"type": "text", "text": "First part. "},
                {"type": "text", "text": "Second part."},
            ]
        )
        result = process_llm_response(response)
        assert result.content == "First part. Second part."

    def test_list_with_reasoning_block_filtered(self):
        response = AIMessage(
            content=[
                {"type": "reasoning", "id": "r1", "summary": []},
                {"type": "text", "text": "Actual answer"},
            ]
        )
        result = process_llm_response(response)
        assert result.content == "Actual answer"
        assert "reasoning" not in result.content

    def test_list_with_string_blocks(self):
        response = AIMessage(content=["Hello ", "World"])
        result = process_llm_response(response)
        assert result.content == "Hello World"

    def test_mixed_blocks(self):
        response = AIMessage(
            content=[
                {"type": "reasoning", "id": "r1", "summary": []},
                {"type": "text", "text": "Answer: "},
                "42",
            ]
        )
        result = process_llm_response(response)
        assert result.content == "Answer: 42"

    def test_empty_list_produces_empty_string(self):
        response = AIMessage(content=[])
        result = process_llm_response(response)
        assert result.content == ""

    def test_only_reasoning_blocks_produces_empty(self):
        response = AIMessage(
            content=[
                {"type": "reasoning", "id": "r1", "summary": []},
            ]
        )
        result = process_llm_response(response)
        assert result.content == ""
