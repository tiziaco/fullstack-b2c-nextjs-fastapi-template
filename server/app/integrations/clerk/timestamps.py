"""Helpers for Clerk payload values.

Clerk expresses every timestamp as a millisecond epoch integer, in both the
Backend API objects and the webhook payloads. The database stores aware UTC
datetimes, so one conversion function serves every caller.
"""

from datetime import UTC, datetime
from typing import Optional

# A user row created from a membership event, or inserted by
# handle_user_created with no usable Clerk timestamp, has never had a
# genuine dated Clerk payload applied to it. Its ordering clock must
# therefore start older than any real event — the epoch, not `None`:
# UserRepository.create()/update_from_clerk() fall back to datetime.now(UTC)
# for a None value, which is *newer* than any pending event and would drop
# it as stale, defeating the point of seeding the row in the first place.
# Shared by webhooks/handlers/user.py and webhooks/handlers/membership.py
# so both draw on one definition.
UNSYNCED_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def clerk_timestamp_to_datetime(value: Optional[int]) -> Optional[datetime]:
    """Convert a Clerk millisecond epoch timestamp to an aware UTC datetime.

    Deliberately tolerant: webhook payloads are attacker-influenced up to the
    signature boundary, and a field of an unexpected type must degrade to
    "unknown" rather than raise inside a handler.

    Args:
        value: Milliseconds since the Unix epoch, or None.

    Returns:
        An aware UTC datetime, or None if the value is absent or not an int.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    except (OverflowError, ValueError, OSError):
        # An in-range int can still be too large (OverflowError) or fall
        # outside datetime's representable year range (ValueError) for
        # fromtimestamp — and some platforms raise OSError for values their
        # C library can't convert. All three are "unusable value", not
        # "malformed payload": degrade to None rather than raise.
        return None
