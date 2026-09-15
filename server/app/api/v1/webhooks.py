"""Clerk webhook endpoint.

Deliberately carries no rate limit. svix bursts on retry, and a 429 reads as
a failed delivery, provoking further retries. The signature check is the gate
and it is cheap.

RLS note: this route writes to the database outside any authenticated user
request. There is no bearer token here, so AuthMiddleware never populates
`request.state.user_id` — it stays at the `None` it initialises for every
request — and `get_db_session` therefore sets no row-level-security
predicate on the session (a NULL passed to `set_config` is a no-op there,
same as on any other unauthenticated request). That is harmless today
because no RLS policy exists yet on the user table. If one is
ever added, this path has no user identity to derive a predicate from and
will need an explicit system/service-role escape hatch, since it writes as
Clerk's push notifications dictate, not on behalf of a signed-in user.
"""

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
)

from app.api.dependencies.database import DbSession
from app.integrations.clerk.webhooks import (
    VerifiedEvent,
    WebhookContext,
    clerk_dispatcher,
    verify_clerk_webhook,
)

router = APIRouter()


@router.post(
    "/clerk",
    status_code=204,
    operation_id="clerkWebhook",
    summary="Clerk webhook receiver",
    include_in_schema=False,
)
async def clerk_webhook(
    verified: Annotated[VerifiedEvent, Depends(verify_clerk_webhook)],
    session: DbSession,
) -> None:
    """Receive a verified Clerk webhook event and dispatch it.

    Args:
        verified: The verified event and its svix delivery id, produced by
            the signature dependency.
        session: Database session.
    """
    await clerk_dispatcher.dispatch(
        WebhookContext(
            event=verified.event,
            message_id=verified.message_id,
            session=session,
        )
    )
