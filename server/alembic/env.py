"""Alembic environment configuration for async migrations."""

import asyncio
import os
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

from alembic import context

# Load environment-specific .env file for host-side runs (`make migrate`).
# override=False so real environment variables always win: inside a container
# the compose `environment:` block sets POSTGRES_HOST=db, and a stray .env file
# (which holds the HOST-side localhost:5434 values) must never redirect
# migrations at a different database than the one the app talks to.
app_env = os.getenv("APP_ENV", "development")
env_file = f".env.{app_env}"
if os.path.exists(env_file):
    load_dotenv(env_file, override=False)
elif os.path.exists(".env"):
    load_dotenv(".env", override=False)

# Import settings after loading .env
from app.core.config import settings
from app.models.conversation import Conversation

# Import all models to register with SQLModel metadata
from app.models.user import User

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata to SQLModel metadata which contains all table definitions
target_metadata = SQLModel.metadata

# Build database URL from settings
database_url = (
    f"postgresql+asyncpg://{settings.database.USER}:"
    f"{settings.database.PASSWORD.get_secret_value()}"
    f"@{settings.database.HOST}:{settings.database.PORT}/{settings.database.DB}"
)

# Override the sqlalchemy.url in alembic config
config.set_main_option("sqlalchemy.url", database_url)


def include_name(name, type_, parent_names):
    """Exclude LangGraph checkpoint tables from autogenerate.

    LangGraph's AsyncPostgresSaver manages its own schema through setup().
    These tables should not be managed by Alembic.

    Args:
        name: Name of the object (table, column, etc.)
        type_: Type of the object ('table', 'column', 'index', etc.)
        parent_names: Parent object names

    Returns:
        bool: True if object should be included, False to exclude
    """
    if type_ == "table":
        # Exclude LangGraph self-managed tables
        excluded_tables = {
            "checkpoints",
            "checkpoint_blobs",
            "checkpoint_writes",
            "checkpoint_migrations",
        }
        return name not in excluded_tables
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the given connection.

    Args:
        connection: SQLAlchemy connection object
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_name=include_name,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in async mode.

    Creates an async engine and runs migrations asynchronously.
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
