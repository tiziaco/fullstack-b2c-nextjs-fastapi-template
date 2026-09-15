"""Clerk webhook dispatch.

Handlers are registered by event type rather than selected with a chain of
conditionals, so each one stays independently testable and the registry
doubles as the list of events this app subscribes to.

Every handler must be idempotent. There is no dedup table: svix supplies
signature validity and a five-minute timestamp tolerance, and within that
window a replay must converge rather than duplicate. See the design spec
for the trigger to revisit that decision — the delivery id that a dedup
table would key on already reaches here on the context, so adding one is a
matter of a store, not another signature change.
"""

from typing import (
    Awaitable,
    Callable,
    Dict,
)

from app.core.logging import logger
from app.integrations.clerk.webhooks.handlers.user import (
    handle_user_created,
    handle_user_deleted,
    handle_user_updated,
)
from app.integrations.clerk.webhooks.schemas import WebhookContext

WebhookHandler = Callable[[WebhookContext], Awaitable[None]]


class ClerkEventDispatcher:
    """Routes verified Clerk events to their handlers."""

    def __init__(self) -> None:
        """Build an empty registry."""
        self._handlers: Dict[str, WebhookHandler] = {}

    def register(self, event_type: str, handler: WebhookHandler) -> None:
        """Register a handler for one Clerk event type.

        Args:
            event_type: The Clerk event string, e.g. "user.created".
            handler: Coroutine taking one WebhookContext.
        """
        self._handlers[event_type] = handler

    async def dispatch(self, ctx: WebhookContext) -> None:
        """Run the handler registered for this event's type.

        An unregistered type is logged and ignored. It must not raise: Clerk
        retries failed deliveries and disables endpoints that keep failing, so
        an error here would eventually cost us the events we do handle.

        Both log lines carry svix's message id, so a line here can be matched
        against the delivery of the same id in Clerk's dashboard.

        Args:
            ctx: The verified event, its delivery id, and the DB session.
        """
        handler = self._handlers.get(ctx.event.type)

        if handler is None:
            logger.info(
                "webhook_event_unhandled",
                event_type=ctx.event.type,
                message_id=ctx.message_id,
            )
            return

        await handler(ctx)
        logger.info(
            "webhook_event_processed",
            event_type=ctx.event.type,
            message_id=ctx.message_id,
        )


clerk_dispatcher = ClerkEventDispatcher()

clerk_dispatcher.register("user.created", handle_user_created)
clerk_dispatcher.register("user.updated", handle_user_updated)
clerk_dispatcher.register("user.deleted", handle_user_deleted)
