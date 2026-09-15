"""Integration test fixtures — real DB, mocked external services, short-circuit auth."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.api.dependencies.agent import get_chatbot_agent
from app.api.dependencies.authentication import get_current_user
from app.main import app
from app.models.user import User
from app.schemas.chat import Message

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def test_user(db_session):
    """Create a test user in the database, rolled back after each test."""
    user = User(
        clerk_id="user_test_integration_abc123",
        email="integration@example.com",
        first_name="Test",
        last_name="User",
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def authenticated_client(client, test_user):
    """HTTP client with get_current_user overridden to return test_user directly.

    Bypasses JWT verification and JIT provisioning entirely.
    The DB session is still active — routes can still write to DB.
    """
    app.dependency_overrides[get_current_user] = lambda: test_user
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def mock_agent():
    """Mock ChatbotAgent with pre-configured async method stubs."""
    agent = MagicMock()
    agent.get_response = AsyncMock(
        return_value=[
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
        ]
    )
    agent.get_chat_history = AsyncMock(
        return_value=[
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
        ]
    )
    agent.llm_service.current_model_name.return_value = "gpt-5-mini"
    agent.is_ready.return_value = True
    return agent


@pytest.fixture
def stub_checkpoint_deletion():
    """Stub LangGraph checkpoint deletion for routes that clear a conversation.

    The checkpoint tables live behind the psycopg pool that agents open at
    startup; no integration test opens it, so a real call blocks until
    PoolTimeout. This used to be stubbed incidentally, via the mocked agent
    that owned clear_chat_history. Now that deletion is a module-level
    function its callers import directly, every importing module needs
    patching by name — the two routes that clear a conversation, and
    UserService.erase_user, which clears the checkpoints of every
    conversation the deleted user owned.

    Yields the erasure path's stub, since that is the one a test asserts on:
    the routes' calls are incidental cleanup, while erase_user's are a
    contractual step of the GDPR cascade.
    """
    with (
        patch("app.api.v1.chatbot.delete_conversation_checkpoints", new=AsyncMock()),
        patch("app.api.v1.conversation.delete_conversation_checkpoints", new=AsyncMock()),
        patch(
            "app.services.user.service.delete_conversation_checkpoints",
            new=AsyncMock(),
        ) as erasure_stub,
    ):
        yield erasure_stub


@pytest_asyncio.fixture
async def authenticated_client_with_agent(authenticated_client, mock_agent):
    """HTTP client with both auth and chatbot agent overridden."""
    app.dependency_overrides[get_chatbot_agent] = lambda: mock_agent
    yield authenticated_client
    app.dependency_overrides.pop(get_chatbot_agent, None)
