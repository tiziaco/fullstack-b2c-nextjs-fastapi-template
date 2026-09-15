"""The memory factory must call mem0's API the way the installed SDK defines it.

`create_memory` is the only place in `app/` that touches `AsyncMemory`
construction, and every caller of it wraps the call in `except Exception` and
logs — a mismatch here degrades to "the agent has no long-term memory" rather
than to a failed request, so nothing in the suite goes red and nothing in the
API response looks wrong. That is exactly how the `await from_config(...)`
break introduced by mem0ai 1.0.10 reached a live chat before being noticed.

These tests pin the sync/async shape of the two halves of that boundary.
"""

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mem0 import AsyncMemory
from mem0.llms.base import LLMBase

import app.agents.shared.memory.factory as factory
from app.core.config import settings

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_singleton():
    """`_memory_instance` is module-level and caches across tests."""
    factory._memory_instance = None
    yield
    factory._memory_instance = None


async def test_create_memory_does_not_await_from_config():
    """`from_config` is a plain classmethod; awaiting its return raises.

    The mock is a MagicMock, not an AsyncMock, so it returns a non-awaitable
    exactly as the real classmethod does. An `await` in the factory fails here
    with the same TypeError it raises against the real SDK.
    """
    sentinel = MagicMock(spec=AsyncMemory)
    fake_cls = MagicMock()
    fake_cls.from_config = MagicMock(return_value=sentinel)

    with patch.object(factory, "AsyncMemory", fake_cls):
        memory = await factory.create_memory()

    assert memory is sentinel
    fake_cls.from_config.assert_called_once()


def test_from_config_is_not_a_coroutine_function():
    """Guards the reverse drift: mem0 making construction async again."""
    assert not inspect.iscoroutinefunction(AsyncMemory.from_config)


@pytest.mark.parametrize("method", ["add", "search", "delete_all"])
def test_the_methods_the_factory_awaits_are_still_async(method: str):
    """`get_relevant_memory`, `update_memory` and `delete_user_memory` await these."""
    assert inspect.iscoroutinefunction(getattr(AsyncMemory, method))


async def test_the_instance_is_built_once_and_reused():
    """`create_memory` caches in a module-level global; construction is costly."""
    fake_cls = MagicMock()
    fake_cls.from_config = MagicMock(return_value=MagicMock(spec=AsyncMemory))

    with patch.object(factory, "AsyncMemory", fake_cls):
        first = await factory.create_memory()
        second = await factory.create_memory()

    assert first is second
    fake_cls.from_config.assert_called_once()


async def test_get_relevant_memory_formats_search_results():
    """Covers the await on `search` against a correctly-constructed instance."""
    instance = MagicMock(spec=AsyncMemory)
    instance.search = AsyncMock(return_value={"results": [{"memory": "likes tea"}, {"memory": "lives in Rome"}]})
    fake_cls = MagicMock()
    fake_cls.from_config = MagicMock(return_value=instance)

    with patch.object(factory, "AsyncMemory", fake_cls):
        result = await factory.get_relevant_memory("user-1", "who am I?")

    assert result == "* likes tea\n* lives in Rome"


async def test_search_passes_the_user_id_in_filters_not_as_a_kwarg():
    """mem0 2.0 rejects a top-level `user_id=` on search().

    `_reject_top_level_entity_params` raises ValueError for it, and
    `get_relevant_memory` swallows exceptions — so calling the 1.x way returns
    an empty string and the agent just quietly forgets everything.
    """
    instance = MagicMock(spec=AsyncMemory)
    instance.search = AsyncMock(return_value={"results": []})
    fake_cls = MagicMock()
    fake_cls.from_config = MagicMock(return_value=instance)

    with patch.object(factory, "AsyncMemory", fake_cls):
        await factory.get_relevant_memory("user-1", "who am I?")

    kwargs = instance.search.await_args.kwargs
    assert kwargs["filters"] == {"user_id": "user-1"}
    assert "user_id" not in kwargs


async def test_search_pins_top_k_and_threshold_explicitly():
    """2.0 changed both defaults (limit 100 -> top_k 20, threshold None -> 0.1).

    Passing them explicitly is what stops the next default flip from silently
    resizing the block of memories pasted into the agent's prompt.
    """
    instance = MagicMock(spec=AsyncMemory)
    instance.search = AsyncMock(return_value={"results": []})
    fake_cls = MagicMock()
    fake_cls.from_config = MagicMock(return_value=instance)

    with patch.object(factory, "AsyncMemory", fake_cls):
        await factory.get_relevant_memory("user-1", "who am I?")

    kwargs = instance.search.await_args.kwargs
    assert kwargs["top_k"] == settings.memory.SEARCH_TOP_K
    assert kwargs["threshold"] == settings.memory.SEARCH_THRESHOLD


def test_search_signature_still_rejects_top_level_entity_ids():
    """Pins the reason the call above is shaped that way, against the real SDK."""
    params = inspect.signature(AsyncMemory.search).parameters
    assert "filters" in params
    assert "top_k" in params
    assert "user_id" not in params


class _ProbeLLM(LLMBase):
    """Concrete LLMBase so the param filter can be exercised without a client."""

    def generate_response(self, messages, tools=None, tool_choice="auto", **kwargs):
        raise NotImplementedError


@pytest.mark.parametrize("model", ["gpt-5-nano", "gpt-5-mini", "gpt-5"])
def test_gpt5_extraction_sends_no_temperature(model: str):
    """The 400 that silently lost every memory write, pinned at the source.

    mem0 2.0 classifies gpt-5-nano/-mini as ordinary models and so sends
    `temperature` and `top_p`, which the gpt-5 family rejects outright:
    "Unsupported value: 'temperature' does not support 0.1 with this model."
    `_add_to_vector_store` turns that into an LLMError, `update_memory` logs
    it, and nothing is ever stored.
    """
    with patch.object(settings.memory, "MODEL", model):
        config = factory._memory_llm_config()

    assert config["is_reasoning_model"] is True

    params = _ProbeLLM(config)._get_supported_params(messages=[{"role": "user", "content": "hi"}])
    assert "temperature" not in params
    assert "top_p" not in params


def test_mem0_alone_would_get_gpt5_wrong():
    """Non-vacuity: without the override mem0 sends the parameters that 400.

    If a future mem0 fixes its heuristic this fails, and the override in
    `_memory_llm_config` can be deleted.
    """
    params = _ProbeLLM({"model": "gpt-5-nano"})._get_supported_params(messages=[{"role": "user", "content": "hi"}])
    assert "temperature" in params


@pytest.mark.parametrize("model", ["gpt-4o-mini", "o3-mini"])
def test_non_gpt5_models_keep_mem0s_own_detection(model: str):
    """The override is set only where mem0 is wrong, never as a blanket."""
    with patch.object(settings.memory, "MODEL", model):
        assert "is_reasoning_model" not in factory._memory_llm_config()


async def test_update_memory_strips_identity_keys_from_metadata():
    """mem0 2.0 warns and drops these; user_id already travels as an argument.

    The graph config handed down from `create_graph_config` carries user_id for
    Langfuse, which is why it reaches `add()` at all.
    """
    instance = MagicMock(spec=AsyncMemory)
    instance.add = AsyncMock(return_value={"results": []})
    fake_cls = MagicMock()
    fake_cls.from_config = MagicMock(return_value=instance)

    metadata = {"user_id": "user-1", "conversation_id": "c-1", "environment": "test"}

    with patch.object(factory, "AsyncMemory", fake_cls):
        await factory.update_memory("user-1", [{"role": "user", "content": "hi"}], metadata)

    kwargs = instance.add.await_args.kwargs
    assert kwargs["user_id"] == "user-1"
    assert kwargs["metadata"] == {"conversation_id": "c-1", "environment": "test"}
