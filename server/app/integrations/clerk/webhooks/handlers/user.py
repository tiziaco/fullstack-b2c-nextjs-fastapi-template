"""Handlers for Clerk user.* webhook events.

All three are idempotent. There is no dedup table, so a replay inside
svix's five-minute tolerance window must converge rather than duplicate.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.integrations.clerk.timestamps import UNSYNCED_EPOCH, clerk_timestamp_to_datetime
from app.integrations.clerk.webhooks.schemas import WebhookContext
from app.models.user import User
from app.services.user import (
    user_repository,
    user_service,
)


def primary_email_from_payload(data: dict) -> Optional[str]:
    """Extract the primary email address from a Clerk user payload.

    The SDK helper takes an SDK object; webhook payloads are plain dicts, so
    this is the dict equivalent.

    Args:
        data: A Clerk user payload.

    Returns:
        The primary email address, or None if the payload has none.
    """
    primary_id = data.get("primary_email_address_id")
    for entry in data.get("email_addresses") or []:
        if entry.get("id") == primary_id:
            return entry.get("email_address")
    return None


def is_primary_email_verified(data: dict) -> bool:
    """Report whether the primary email address is verified.

    Args:
        data: A Clerk user payload.

    Returns:
        True only when the primary address exists and is verified.
    """
    primary_id = data.get("primary_email_address_id")
    for entry in data.get("email_addresses") or []:
        if entry.get("id") == primary_id:
            return (entry.get("verification") or {}).get("status") == "verified"
    return False


async def _apply_profile(
    session: AsyncSession,
    user: User,
    data: dict,
    event_ts: Optional[datetime],
) -> None:
    """Apply a profile snapshot, unless the event predates our last sync.

    Clerk guarantees no ordering, so two updates can arrive reversed. The
    comparison is strict: an identical timestamp is applied rather than
    dropped, because the write is idempotent and a same-millisecond distinct
    event is the worse thing to lose.

    Args:
        session: DB session.
        user: The user to update.
        data: The Clerk user payload.
        event_ts: The payload's updated_at, or None if absent/unusable.
    """
    if event_ts is not None and event_ts < user.last_synced_at:
        logger.info(
            "webhook_event_stale",
            clerk_id=user.clerk_id,
            event_ts=event_ts.isoformat(),
            last_synced_at=user.last_synced_at.isoformat(),
        )
        return

    # UserRepository.update_from_clerk() falls back to the host clock (now())
    # whenever last_synced_at is None — that fallback exists for the JIT path,
    # which has no Clerk event to draw a timestamp from. On the webhook path
    # an absent/unusable event_ts must NOT trigger that fallback: writing a
    # host-clock value into last_synced_at would contaminate this same
    # ordering guard for every later event on this row (a fast local clock
    # would then make every future legitimate event look stale forever). So
    # when we have no Clerk timestamp, pass the row's current value through
    # unchanged rather than letting the repository advance it to now().
    await user_repository.update_from_clerk(
        session=session,
        user=user,
        email=primary_email_from_payload(data),
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        avatar_url=data.get("image_url"),
        email_verified=is_primary_email_verified(data),
        last_synced_at=event_ts or user.last_synced_at,
    )


async def handle_user_created(ctx: WebhookContext) -> None:
    """Create the user row, or apply the payload as an update if it exists.

    Safe to handle unconditionally only because the Clerk instance is
    invitation-only. If public sign-up is ever enabled this becomes an
    unauthenticated row-creation vector and must be gated on membership.

    Insertion is additionally gated on the user still existing in Clerk.
    anonymize_user() rewrites clerk_id, so an erased user is indistinguishable
    from one who never existed — the asymmetry handle_user_updated declines on.
    A delivery redelivered after the deletion would otherwise re-insert the
    payload's email and names.

    Args:
        ctx: The verified event, its delivery id, and the DB session.
    """
    data = ctx.data
    session = ctx.session
    clerk_id = data.get("id")
    email = primary_email_from_payload(data)

    if not clerk_id or not email:
        logger.warning("webhook_user_created_incomplete", clerk_id=clerk_id, has_email=bool(email))
        return

    event_ts = clerk_timestamp_to_datetime(data.get("updated_at"))
    user = await user_repository.get_by_clerk_id(session, clerk_id)

    if user is None:
        # Deliberately below get_by_clerk_id: the common case (the row is
        # already there) spends no Clerk call, so this costs roughly one
        # call per genuinely new user rather than one per delivery.
        if not await user_service.exists_in_clerk(clerk_id):
            logger.info("webhook_user_created_absent_in_clerk", clerk_id=clerk_id)
            return

        user = await user_repository.create_or_get(
            session=session,
            clerk_id=clerk_id,
            email=email,
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            avatar_url=data.get("image_url"),
            email_verified=is_primary_email_verified(data),
            # Never let UserRepository.create()'s None fallback write the
            # host clock here: that is the exact contamination _apply_profile
            # and UNSYNCED_EPOCH both exist to prevent. When event_ts is absent or
            # unusable, seed the epoch instead so a fast host clock can never
            # make a later, genuine event look stale.
            last_synced_at=event_ts or UNSYNCED_EPOCH,
        )
        logger.info("webhook_user_created", user_id=user.id, clerk_id=clerk_id)
    else:
        # A replay, or a create arriving after an update. Converge rather
        # than conflict.
        await _apply_profile(session, user, data, event_ts)


async def handle_user_updated(ctx: WebhookContext) -> None:
    """Apply a profile update. Never creates a row.

    An unknown clerk_id has two indistinguishable causes: the create event has
    not landed, or the user was erased — anonymize_user() rewrites clerk_id,
    so an erased user looks exactly like one who never existed. Creating here
    would resurrect deleted users, so the handler declines.

    Args:
        ctx: The verified event, its delivery id, and the DB session.
    """
    data = ctx.data
    session = ctx.session
    clerk_id = data.get("id")
    if not clerk_id:
        logger.warning("webhook_user_updated_incomplete")
        return

    user = await user_repository.get_by_clerk_id(session, clerk_id)
    if user is None:
        logger.warning("webhook_user_updated_unknown", clerk_id=clerk_id)
        return

    await _apply_profile(session, user, data, clerk_timestamp_to_datetime(data.get("updated_at")))


async def handle_user_deleted(ctx: WebhookContext) -> None:
    """Run the full GDPR erasure cascade.

    Anonymising the row alone would orphan LangGraph checkpoints and mem0
    memories with no user row left pointing at them, so nothing would ever
    clean them up — a hole that opens only on the dashboard-initiated path.

    No ordering guard: the payload is a DeletedObjectJSON with no updated_at,
    and deletion is self-protecting. After erasure clerk_id is rewritten, so
    any later event for the original id finds no row.

    Args:
        ctx: The verified event, its delivery id, and the DB session.
    """
    data = ctx.data
    session = ctx.session
    clerk_id = data.get("id")
    if not clerk_id:
        logger.warning("webhook_user_deleted_incomplete")
        return

    user = await user_repository.get_by_clerk_id(session, clerk_id)
    if user is None:
        # Either the echo of our own DELETE /me, or a replay. Both benign.
        logger.info("webhook_user_deleted_noop", clerk_id=clerk_id)
        return

    await user_service.erase_user(user, session)
    logger.info("webhook_user_erased", clerk_id=clerk_id)
