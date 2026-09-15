"""PostgreSQL checkpointing utilities for LangGraph agents."""

import asyncio
from typing import Optional
from urllib.parse import quote_plus

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from app.core.config import settings
from app.core.logging import logger

_connection_pool: Optional[AsyncConnectionPool] = None
_checkpointer: Optional[AsyncPostgresSaver] = None
_checkpointer_lock = asyncio.Lock()


async def create_connection_pool() -> AsyncConnectionPool:
    """Create and return a PostgreSQL connection pool.

    Uses singleton pattern - creates once and returns cached instance on subsequent calls.

    Returns:
        AsyncConnectionPool: A connection pool for PostgreSQL database.

    Raises:
        Exception: If pool creation or opening fails.
    """
    global _connection_pool

    if _connection_pool is None:
        # Fixed pool size for checkpointing (total allocation: 30 max connections)
        # SQLAlchemy: 20 (15+5 overflow), Checkpointer: 5, mem0: ~5
        max_size = 5

        connection_url = (
            "postgresql://"
            f"{quote_plus(settings.database.USER)}:{quote_plus(settings.database.PASSWORD.get_secret_value())}"
            f"@{settings.database.HOST}:{settings.database.PORT}/{settings.database.DB}"
        )

        _connection_pool = AsyncConnectionPool(
            connection_url,
            open=False,
            max_size=max_size,
            kwargs={
                "autocommit": True,
                "connect_timeout": 5,
                "prepare_threshold": None,
            },
        )
        await _connection_pool.open()
        logger.info("connection_pool_created", max_size=max_size, environment=settings.ENVIRONMENT.value)

    return _connection_pool


async def create_postgres_saver() -> AsyncPostgresSaver:
    """Create and setup an AsyncPostgresSaver for LangGraph checkpointing.

    Uses singleton pattern with async lock to ensure only one setup runs.
    Safe for concurrent access - subsequent calls return the cached instance.

    Returns:
        AsyncPostgresSaver: Configured checkpointer instance.

    Raises:
        Exception: If checkpointer setup fails or times out.
    """
    global _checkpointer

    # Fast path: return existing checkpointer without acquiring lock
    if _checkpointer is not None:
        return _checkpointer

    # Slow path: acquire lock and initialize
    async with _checkpointer_lock:
        # Double-check after acquiring lock (another coroutine might have initialized it)
        if _checkpointer is not None:
            return _checkpointer

        connection_pool = await create_connection_pool()
        checkpointer = AsyncPostgresSaver(connection_pool)

        # Add timeout to prevent indefinite hanging (increased to 30s for migrations)
        await asyncio.wait_for(checkpointer.setup(), timeout=30.0)
        logger.info("checkpointer_setup_completed", environment=settings.ENVIRONMENT.value)

        _checkpointer = checkpointer
        return _checkpointer


async def delete_conversation_checkpoints(conversation_id: str) -> None:
    """Hard-delete every checkpoint row for one conversation thread.

    Checkpoints are keyed by thread_id in a single set of tables shared by
    every agent, so this is a property of the checkpoint store rather than of
    any agent instance. Callers that hold an agent gain nothing by going
    through it.

    Args:
        conversation_id: The thread_id whose rows are removed.

    Raises:
        Exception: If the pool is unavailable or a DELETE fails.
    """
    # Singleton - already initialized at startup
    conn_pool = await create_connection_pool()

    async with conn_pool.connection() as conn:
        for table in settings.database.CHECKPOINT_TABLES:
            await conn.execute(f"DELETE FROM {table} WHERE thread_id = %s", (conversation_id,))
            logger.info("cleared_table_for_conversation", table=table, conversation_id=conversation_id)


async def close_connection_pool() -> None:
    """Close the connection pool if it exists."""
    global _connection_pool, _checkpointer

    if _connection_pool is not None:
        try:
            await _connection_pool.close()
            _checkpointer = None  # Reset checkpointer when pool closes
            logger.info("connection_pool_closed")
            _connection_pool = None
        except Exception as e:
            logger.exception("failed_to_close_connection_pool", error=str(e))
