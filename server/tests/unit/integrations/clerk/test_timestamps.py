"""Clerk sends millisecond epoch integers; the DB column is aware UTC."""

from datetime import UTC, datetime

import pytest

from app.integrations.clerk.timestamps import clerk_timestamp_to_datetime

pytestmark = pytest.mark.unit


def test_converts_millisecond_epoch_to_aware_utc():
    result = clerk_timestamp_to_datetime(1654012591835)
    assert result == datetime(2022, 5, 31, 15, 56, 31, 835000, tzinfo=UTC)
    assert result.tzinfo is not None


def test_none_passes_through():
    assert clerk_timestamp_to_datetime(None) is None


def test_non_integer_input_returns_none():
    """Defensive: a payload field of an unexpected type must not raise."""
    assert clerk_timestamp_to_datetime("1654012591835") is None


def test_overflow_value_returns_none():
    """An in-range int type but a value too large for datetime.fromtimestamp
    must degrade to None rather than raise OverflowError. Signature-gated so
    only Clerk itself can trigger this, but an unhandled raise here would be
    a 500 that Clerk retries and eventually disables the endpoint over."""
    assert clerk_timestamp_to_datetime(10**30) is None


def test_out_of_range_year_returns_none():
    """A value in datetime.fromtimestamp's numeric range but past its
    representable year range raises ValueError, not OverflowError — both
    must degrade to None."""
    assert clerk_timestamp_to_datetime(99999999999999999) is None
