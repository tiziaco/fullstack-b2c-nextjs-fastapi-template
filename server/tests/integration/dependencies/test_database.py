"""Integration tests for get_db_session dependency — error translation and RLS context."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError

from app.api.dependencies.database import _integrity_diagnostics, get_db_session
from app.exceptions.base import (
    DatabaseConflictError,
    DatabaseConnectionError,
    DatabaseError,
)
from app.models.user import User

pytestmark = pytest.mark.integration


def _make_mock_request(with_user_id: bool = False):
    """Create a mock FastAPI request with session_factory on app state."""
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    mock_request = MagicMock()
    mock_request.app.state.session_factory.return_value = mock_session

    if with_user_id:
        mock_request.state.user_id = "test-user-uuid"
    else:
        # Remove user_id attribute so hasattr returns False
        del mock_request.state.user_id

    return mock_request, mock_session


class TestErrorTranslation:
    """Tests for SQLAlchemy error → domain exception mapping."""

    @patch("app.api.dependencies.database.clear_session_context", new_callable=AsyncMock)
    @patch("app.api.dependencies.database.set_session_context", new_callable=AsyncMock)
    async def test_integrity_error_raises_database_conflict(self, mock_set, mock_clear):
        """IntegrityError → DatabaseConflictError (409)."""
        mock_request, mock_session = _make_mock_request()
        orig_exc = Exception("unique constraint violation")
        mock_session.commit.side_effect = IntegrityError("INSERT ...", {}, orig_exc)

        gen = get_db_session(mock_request)
        await gen.__anext__()  # yields session

        with pytest.raises(DatabaseConflictError):
            await gen.athrow(IntegrityError("INSERT ...", {}, orig_exc))

    @patch("app.api.dependencies.database.clear_session_context", new_callable=AsyncMock)
    @patch("app.api.dependencies.database.set_session_context", new_callable=AsyncMock)
    async def test_operational_error_raises_database_connection_error(self, mock_set, mock_clear):
        """OperationalError → DatabaseConnectionError (503)."""
        mock_request, mock_session = _make_mock_request()
        orig_exc = Exception("connection refused")
        mock_session.commit.side_effect = OperationalError("SELECT ...", {}, orig_exc)

        gen = get_db_session(mock_request)
        await gen.__anext__()

        with pytest.raises(DatabaseConnectionError):
            await gen.athrow(OperationalError("SELECT ...", {}, orig_exc))

    @patch("app.api.dependencies.database.clear_session_context", new_callable=AsyncMock)
    @patch("app.api.dependencies.database.set_session_context", new_callable=AsyncMock)
    async def test_dbapi_error_raises_database_error(self, mock_set, mock_clear):
        """DBAPIError → DatabaseError (500)."""
        mock_request, mock_session = _make_mock_request()
        orig_exc = Exception("dbapi error")
        mock_session.commit.side_effect = DBAPIError("...", {}, orig_exc)

        gen = get_db_session(mock_request)
        await gen.__anext__()

        with pytest.raises(DatabaseError):
            await gen.athrow(DBAPIError("...", {}, orig_exc))


class TestIntegrityDiagnostics:
    """Tests for the constraint/SQLSTATE extraction behind the 409 log line.

    The mock-based tests above pass a bare Exception as `orig`, which is what
    let a psycopg-shaped `.diag` lookup survive on an asyncpg stack: it
    silently returned None, and the log line read `constraint=unknown` on
    every conflict. The first test here is therefore the load-bearing one —
    it provokes a genuine unique violation so the assertion runs against a
    real driver exception rather than a hand-built stand-in.
    """

    async def test_reads_the_constraint_from_a_real_asyncpg_violation(self, db_session, test_user):
        """The regression test: a real 23505 must yield a real constraint name.

        postgres_container runs with driver="asyncpg" (tests/conftest.py), so
        this reproduces production's error shape exactly. asyncpg carries the
        PG error fields on the exception SQLAlchemy's adapter chains to, not
        on `orig` itself.
        """
        duplicate = User(
            clerk_id="user_duplicate_email",
            email=test_user.email,
        )
        db_session.add(duplicate)

        with pytest.raises(IntegrityError) as caught:
            await db_session.flush()
        # A failed flush leaves the savepoint unusable for anything after it.
        await db_session.rollback()

        constraint, sqlstate = _integrity_diagnostics(caught.value)

        # Loose on the name so renaming the index (ix_user_email today) fails
        # the migration review rather than this test.
        assert constraint is not None
        assert "email" in constraint
        assert sqlstate == "23505"  # unique_violation

    def test_reads_the_constraint_from_the_psycopg_shape(self):
        """The other driver's layout, kept so a driver swap stays covered."""
        orig = MagicMock()
        orig.diag.constraint_name = "ix_user_email"
        orig.sqlstate = "23505"

        assert _integrity_diagnostics(IntegrityError("INSERT ...", {}, orig)) == (
            "ix_user_email",
            "23505",
        )

    def test_returns_none_when_the_error_carries_no_diagnostics(self):
        """Degrades to (None, None) rather than raising inside the handler."""
        assert _integrity_diagnostics(IntegrityError("INSERT ...", {}, Exception("no fields"))) == (None, None)


class TestRLSContext:
    """Tests for RLS context setup and cleanup."""

    @patch("app.api.dependencies.database.clear_session_context", new_callable=AsyncMock)
    @patch("app.api.dependencies.database.set_session_context", new_callable=AsyncMock)
    async def test_set_context_called_when_user_id_present(self, mock_set, mock_clear):
        mock_request, mock_session = _make_mock_request(with_user_id=True)

        gen = get_db_session(mock_request)
        await gen.__anext__()
        try:
            await gen.aclose()
        except StopAsyncIteration:
            pass

        mock_set.assert_called_once_with(mock_session, "test-user-uuid")

    @patch("app.api.dependencies.database.clear_session_context", new_callable=AsyncMock)
    @patch("app.api.dependencies.database.set_session_context", new_callable=AsyncMock)
    async def test_clear_context_always_called(self, mock_set, mock_clear):
        """clear_session_context must run even when an exception occurs."""
        mock_request, mock_session = _make_mock_request()
        orig_exc = Exception("boom")
        mock_session.commit.side_effect = IntegrityError("...", {}, orig_exc)

        gen = get_db_session(mock_request)
        await gen.__anext__()
        try:
            await gen.athrow(IntegrityError("...", {}, orig_exc))
        except DatabaseConflictError:
            pass

        mock_clear.assert_called_once()
