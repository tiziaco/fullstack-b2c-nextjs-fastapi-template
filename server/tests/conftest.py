"""Shared test fixtures and configuration.

This module provides pytest fixtures for testing the FastAPI application,
including test database setup, HTTP clients, and authentication helpers.
"""

import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from testcontainers.community.postgres import PostgresContainer

# Set test environment and load .env.test into os.environ BEFORE importing app.
# This is required because nested pydantic-settings models (DatabaseSettings, etc.)
# have their own SettingsConfigDict without env_file, so they only read os.environ.
os.environ["APP_ENV"] = "test"

from dotenv import load_dotenv

load_dotenv(".env.test", override=True)

from app.api.dependencies.database import get_db_session
from app.core.config import settings
from app.main import app

# Event loop is managed by pytest-asyncio via asyncio_default_fixture_loop_scope = session
# in pytest.ini. No custom event_loop fixture needed.


# ============================================================================
# Database Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def postgres_container():
    """Run a throwaway PostgreSQL for the test session.

    Session-scoped and lazy: only `test_engine` depends on it, and only
    integration tests reach `test_engine` (via `db_session`), so a unit-test
    run never starts a container.

    Uses the same pgvector image as dev/prod for parity — no model declares a
    vector column today, so the extension is not required, but the image is
    already present locally and keeps the versions aligned.

    Requires a running Docker daemon. The container gets an ephemeral host
    port, so it can never collide with the dev database.
    """
    with PostgresContainer("pgvector/pgvector:pg16", driver="asyncpg") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def test_database_url(postgres_container) -> str:
    """Get the connection URL of the throwaway test database.

    Returns:
        str: PostgreSQL connection URL for testing
    """
    return postgres_container.get_connection_url()


@pytest_asyncio.fixture(scope="session")
async def test_engine(test_database_url: str):
    """Create async test database engine.

    Creates all tables at session start and drops them at session end. The
    database lives in a throwaway container (see `postgres_container`), so it
    starts empty every run and cannot touch development data.

    Args:
        test_database_url: Database connection URL

    Yields:
        AsyncEngine: SQLAlchemy async engine for testing
    """
    engine = create_async_engine(
        test_database_url,
        echo=False,  # Set to True for SQL query debugging
        future=True,
        pool_pre_ping=True,  # Verify connections before using
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    yield engine

    # Drop all tables after tests
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a new database session for each test.

    Uses an outer transaction on the raw connection that is always rolled back,
    while the session operates with savepoints. This means tests can freely call
    session.add(), session.commit(), session.refresh() — all writes are undone
    after the test finishes.

    Args:
        test_engine: Async database engine

    Yields:
        AsyncSession: Database session for testing
    """
    async with test_engine.connect() as conn:
        # Start an outer transaction — will be rolled back after the test
        trans = await conn.begin()

        # Session uses savepoints so commit() doesn't touch the outer transaction
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

        yield session

        await session.close()
        await trans.rollback()


# ============================================================================
# FastAPI Client Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def client(test_engine, db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP test client with database session override.

    Injects the test engine into app.state so endpoints that read
    request.app.state.engine (e.g. /health) work without the lifespan.
    Database operations are automatically rolled back after each test.

    Args:
        test_engine: Session-scoped async engine (sets app.state.engine)
        db_session: Test database session (overrides the DB dependency)

    Yields:
        AsyncClient: HTTPX async client for testing
    """
    app.state.engine = test_engine

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def unauthenticated_client(test_engine) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP test client without authentication.

    Injects the test engine into app.state so public endpoints that read
    request.app.state.engine (e.g. /health) work without the lifespan.

    Args:
        test_engine: Session-scoped async engine (sets app.state.engine)

    Yields:
        AsyncClient: HTTPX async client without auth headers
    """
    app.state.engine = test_engine

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ============================================================================
# Authentication Fixtures
# ============================================================================


@pytest.fixture
def mock_clerk_user_id() -> str:
    """Mock Clerk user ID for testing.

    Returns:
        str: Test user ID
    """
    return "user_test_123456789"


@pytest.fixture
def mock_jwt_token(mock_clerk_user_id: str) -> str:
    """Mock JWT token for authenticated requests.

    In a real implementation, you'd generate a proper JWT here.
    For now, we'll mock the authentication middleware.

    Args:
        mock_clerk_user_id: Test user ID

    Returns:
        str: Mock JWT token
    """
    # TODO: Generate actual test JWT if needed
    return "mock_jwt_token_for_testing"


@pytest.fixture
def auth_headers(mock_jwt_token: str) -> dict:
    """Create authorization headers for authenticated requests.

    Args:
        mock_jwt_token: JWT token

    Returns:
        dict: Headers with Authorization bearer token

    Example:
        ```python
        async def test_protected_endpoint(client, auth_headers):
            response = await client.get("/api/v1/me", headers=auth_headers)
            assert response.status_code == 200
        ```
    """
    return {"Authorization": f"Bearer {mock_jwt_token}"}


# ============================================================================
# Mock Service Fixtures
# ============================================================================


@pytest.fixture
def mock_openai_response():
    """Mock OpenAI API response for LLM testing.

    Returns:
        dict: Mock completion response
    """
    return {
        "id": "chatcmpl-test123",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "gpt-5-mini",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "This is a test response from the AI assistant.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        },
    }


# ============================================================================
# Utility Fixtures
# ============================================================================


@pytest.fixture
def sample_chat_message() -> dict:
    """Sample chat message payload for testing.

    Returns:
        dict: Chat message request body
    """
    return {
        "content": "Hello, how are you?",
        "conversation_id": "test_conversation_123",
    }


@pytest.fixture(autouse=True)
def reset_app_state():
    """Reset application state before each test.

    This ensures tests don't interfere with each other through shared state.
    Runs automatically before every test.
    """
    # Clear any dependency overrides
    app.dependency_overrides.clear()

    yield

    # Cleanup after test
    app.dependency_overrides.clear()


# ============================================================================
# Markers Configuration
# ============================================================================


def pytest_configure(config):
    """Configure pytest markers.

    This allows us to mark tests with custom markers like:
    - @pytest.mark.unit - Fast unit tests
    - @pytest.mark.integration - Integration tests with database
    - @pytest.mark.slow - Slow tests (e.g., LLM calls)
    - @pytest.mark.asyncio - Async tests (provided by pytest-asyncio)
    """
    config.addinivalue_line("markers", "unit: Unit tests that don't require database or external services")
    config.addinivalue_line("markers", "integration: Integration tests that use database or external services")
    config.addinivalue_line("markers", "slow: Slow tests that make external API calls")
    config.addinivalue_line("markers", "asyncio: Async tests using pytest-asyncio")
