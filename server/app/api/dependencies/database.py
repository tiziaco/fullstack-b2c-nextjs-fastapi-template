"""Database session dependencies for FastAPI endpoints."""

from typing import (
    Annotated,
    AsyncGenerator,
    Optional,
)

from fastapi import (
    Depends,
    Request,
)
from sqlalchemy.exc import (
    DBAPIError,
    IntegrityError,
    OperationalError,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.database.context import (
    clear_session_context,
    set_session_context,
)
from app.exceptions.base import (
    DatabaseConflictError,
    DatabaseConnectionError,
    DatabaseError,
)


def _integrity_diagnostics(exc: IntegrityError) -> tuple[Optional[str], Optional[str]]:
    """Pull the constraint name and SQLSTATE out of an IntegrityError.

    The drivers hide them in different places, and only one branch is ever
    right: psycopg puts them on `orig.diag`; asyncpg does not, because
    SQLAlchemy's dialect raises its own DBAPI error carrying only pgcode
    `from` the asyncpg one, so constraint_name lives on `orig.__cause__`. This
    app runs asyncpg, so the second branch is the live one — a `.diag` lookup
    alone silently returns None here, which is what motivated the helper.

    Never widen to `orig.detail` or `str(exc)`: both carry the offending values
    ("Key (email)=(...) already exists.", SQLAlchemy's "[parameters: ...]"
    suffix), which is the PII the caller is careful not to log.
    """
    orig = exc.orig
    diag = getattr(orig, "diag", None)
    constraint = getattr(diag, "constraint_name", None) if diag is not None else None
    if constraint is None:
        constraint = getattr(getattr(orig, "__cause__", None), "constraint_name", None)
    return constraint, getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Core dependency for database sessions."""
    if not hasattr(request.app.state, "session_factory"):
        logger.error("session_factory_not_initialized")
        raise RuntimeError("Database session factory not initialized")

    session = request.app.state.session_factory()
    try:
        # Set RLS context if user is authenticated
        if hasattr(request.state, "user_id"):
            await set_session_context(session, request.state.user_id)

        yield session
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        # logger.error(), not .exception(), against this repo's usual
        # traceback-preserving convention (server/CLAUDE.md): the traceback ends
        # in str(e) — SQLAlchemy's "[parameters: ...]" suffix — which on a
        # unique violation over a PII column puts that value in the logs. The
        # constraint name is the actionable non-PII datum, and correlation_id
        # still ties the record to its request. It stays out of the raised
        # exception's context, which reaches API clients.
        constraint, sqlstate = _integrity_diagnostics(e)
        logger.error(
            "database_integrity_error",
            constraint=constraint or "unknown",
            sqlstate=sqlstate,
        )
        raise DatabaseConflictError(
            "Database constraint violation",
        ) from e
    except OperationalError as e:
        await session.rollback()
        logger.exception("database_operational_error", error=str(e))
        raise DatabaseConnectionError(
            "Database connection or operational error",
        ) from e
    except DBAPIError as e:
        await session.rollback()
        logger.exception("database_api_error", error=str(e))
        raise DatabaseError(
            "Database API error",
        ) from e
    except Exception as e:
        await session.rollback()
        logger.exception("database_session_error", error=str(e))
        raise
    finally:
        # Clear RLS context to prevent leaking to pooled connections
        await clear_session_context(session)
        await session.close()


DbSession = Annotated[AsyncSession, Depends(get_db_session)]
