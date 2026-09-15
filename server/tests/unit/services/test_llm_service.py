"""Tests for app.services.llm.service.LLMService — retry logic and fallback chain."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableBinding
from langchain_core.tools import tool
from openai import APIError, APITimeoutError, RateLimitError

from app.core.config import settings
from app.services.llm.exceptions import (
    LLMAPIError,
    LLMFallbackExhaustedError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.services.llm.service import LLMRegistry, LLMService

pytestmark = pytest.mark.unit


@pytest.fixture
def messages():
    return [HumanMessage(content="Hello")]


@tool
def echo(text: str) -> str:
    """Echo the input."""
    return text


def _bound_tool_names(llm) -> list[str]:
    return [t["function"]["name"] for t in llm.kwargs["tools"]]


def _other_model(service: LLMService) -> str:
    """A registry model that is not the one `service` is currently on."""
    names = LLMRegistry.get_all_names()
    return names[(service._current_model_index + 1) % len(names)]


class TestLLMServiceInit:
    """Tests for LLMService initialization."""

    def test_default_model_found(self):
        service = LLMService()
        assert LLMRegistry.get_all_names()[service._current_model_index] == settings.llm.DEFAULT_LLM_MODEL

    def test_no_client_is_built_until_asked_for(self):
        """__init__ must not construct a client.

        It runs at import via the module-level `llm_service` singleton, and
        constructing a client is what requires a credential.
        """
        service = LLMService()
        assert service._llm is None

    def test_get_llm_returns_instance(self):
        service = LLMService()
        assert service.get_llm() is not None

    def test_bind_tools_binds_after_lazy_resolution(self):
        """bind_tools must resolve the client before binding.

        `_llm` is None until something asks for it, so a bare `if self._llm:`
        guard would bind nothing — leaving ChatbotAgent, which calls this once
        at construction, without its tools.
        """
        bound = LLMService().bind_tools([echo]).get_llm()
        assert isinstance(bound, RunnableBinding)


class TestLLMServiceCall:
    """Tests for LLMService.call() — success and fallback scenarios."""

    @pytest.mark.asyncio
    async def test_success_on_first_try(self, messages):
        service = LLMService()
        expected = AIMessage(content="Hello back!")

        with patch.object(service, "_call_llm_with_retry", new_callable=AsyncMock, return_value=expected):
            result = await service.call(messages)

        assert result.content == "Hello back!"

    @pytest.mark.asyncio
    async def test_fallback_after_rate_limit(self, messages):
        service = LLMService()
        expected = AIMessage(content="Fallback response")

        call_count = 0

        async def mock_retry(msgs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RateLimitError(
                    message="rate limited",
                    response=MagicMock(status_code=429, headers={}),
                    body=None,
                )
            return expected

        with patch.object(service, "_call_llm_with_retry", side_effect=mock_retry):
            result = await service.call(messages)

        assert result.content == "Fallback response"
        assert call_count == 2  # Tried 2 models

    @pytest.mark.asyncio
    async def test_all_models_rate_limited_raises(self, messages):
        service = LLMService()

        async def always_rate_limit(msgs):
            raise RateLimitError(
                message="rate limited",
                response=MagicMock(status_code=429, headers={}),
                body=None,
            )

        with patch.object(service, "_call_llm_with_retry", side_effect=always_rate_limit):
            with pytest.raises(LLMRateLimitError):
                await service.call(messages)

    @pytest.mark.asyncio
    async def test_all_models_timeout_raises(self, messages):
        service = LLMService()

        async def always_timeout(msgs):
            raise APITimeoutError(request=MagicMock())

        with patch.object(service, "_call_llm_with_retry", side_effect=always_timeout):
            with pytest.raises(LLMTimeoutError):
                await service.call(messages)

    @pytest.mark.asyncio
    async def test_all_models_api_error_raises(self, messages):
        service = LLMService()

        async def always_api_error(msgs):
            raise APIError(
                message="server error",
                request=MagicMock(),
                body=None,
            )

        with patch.object(service, "_call_llm_with_retry", side_effect=always_api_error):
            with pytest.raises(LLMAPIError):
                await service.call(messages)

    @pytest.mark.asyncio
    async def test_pinned_model_keeps_tools(self, messages):
        """A `model_name=` override must resolve a client with the tools bound."""
        service = LLMService().bind_tools([echo])
        seen = {}

        async def capture(msgs):
            seen["llm"] = service.get_llm()
            return AIMessage(content="ok")

        with patch.object(service, "_call_llm_with_retry", side_effect=capture):
            await service.call(messages, model_name=_other_model(service))

        assert isinstance(seen["llm"], RunnableBinding)
        assert _bound_tool_names(seen["llm"]) == ["echo"]

    @pytest.mark.asyncio
    async def test_pinned_model_does_not_persist(self, messages):
        """A pinned model applies to its own call and no others.

        `llm_service` is a module-level singleton shared by every request, so an
        override left in place would retarget all subsequent traffic until the
        process restarted.
        """
        service = LLMService()
        before_llm, before_index = service.get_llm(), service._current_model_index

        with patch.object(
            service, "_call_llm_with_retry", new_callable=AsyncMock, return_value=AIMessage(content="ok")
        ):
            await service.call(messages, model_name=_other_model(service))

        assert service._llm is before_llm
        assert service._current_model_index == before_index

    @pytest.mark.asyncio
    async def test_pinned_model_restored_when_the_call_raises(self, messages):
        """The restore is in a `finally`, so an escaping error must not leak the pin.

        The error here is deliberately not an `OpenAIError`: those are caught by
        the fallback ladder, which rotates through every model and wraps back to
        the starting index, restoring the state by coincidence and proving
        nothing. A `RuntimeError` — what `_call_llm_with_retry` raises when the
        client is missing — escapes `call()` mid-flight, which is the case only
        a `finally` covers.
        """
        service = LLMService()
        before_llm, before_index = service.get_llm(), service._current_model_index

        async def boom(msgs):
            raise RuntimeError("llm not initialized")

        with patch.object(service, "_call_llm_with_retry", side_effect=boom):
            with pytest.raises(RuntimeError):
                await service.call(messages, model_name=_other_model(service))

        assert service._llm is before_llm
        assert service._current_model_index == before_index


class TestLLMServiceModelSwitching:
    """Tests for circular model switching."""

    def test_next_model_index_wraps(self):
        service = LLMService()
        total = len(LLMRegistry.LLMS)
        service._current_model_index = total - 1

        next_idx = service._get_next_model_index()
        assert next_idx == 0

    def test_switch_to_next_model(self):
        service = LLMService()
        original_index = service._current_model_index

        success = service._switch_to_next_model()

        assert success is True
        assert service._current_model_index != original_index

    def test_switch_preserves_bound_tools(self):
        """A model switch must not drop the tools.

        `_switch_to_next_model` used to overwrite `_llm` with a bare registry
        client. ChatbotAgent binds once at construction and never re-binds, so
        the first fallback rotation left the agent toolless for the rest of the
        process — silently, since the graph routes on an empty `tool_calls`
        rather than raising.
        """
        service = LLMService().bind_tools([echo])

        assert service._switch_to_next_model() is True

        switched = service.get_llm()
        assert isinstance(switched, RunnableBinding)
        assert _bound_tool_names(switched) == ["echo"]
