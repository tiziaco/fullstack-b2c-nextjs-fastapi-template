"""Database engine initialization and management."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import (
    Environment,
    settings,
)
from app.core.logging import logger


async def initialize_database_engine() -> AsyncEngine:
    """Initialize and configure the async database engine."""
    connection_url = (
        f"postgresql+asyncpg://{settings.database.USER}:{settings.database.PASSWORD.get_secret_value()}"
        f"@{settings.database.HOST}:{settings.database.PORT}/{settings.database.DB}"
    )

    engine = create_async_engine(
        connection_url,
        pool_pre_ping=True,
        pool_size=settings.database.POOL_SIZE,
        max_overflow=settings.database.MAX_OVERFLOW,
        pool_timeout=30,
        pool_recycle=1800,
        echo=False,  # Set to True only when debugging SQL queries
    )

    logger.info(
        "database_engine_initialized",
        pool_size=settings.database.POOL_SIZE,
        max_overflow=settings.database.MAX_OVERFLOW,
        environment=settings.ENVIRONMENT.value,
    )

    await test_database_connection(engine)

    return engine


async def test_database_connection(engine: AsyncEngine) -> None:
    """Test the connection. Outside production a failure is fatal."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("database_connection_test_successful")
    except Exception as e:
        logger.exception("database_connection_test_failed", error=str(e))
        if settings.ENVIRONMENT != Environment.PRODUCTION:
            raise


async def close_database_engine(engine: AsyncEngine) -> None:
    """Close all database connections."""
    if engine:
        await engine.dispose()
        logger.info("database_engine_closed")


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker:
    """Create an async session factory."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def health_check(engine: AsyncEngine) -> bool:
    """Check database connection health."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.exception("database_health_check_failed", error=str(e))
        return False
