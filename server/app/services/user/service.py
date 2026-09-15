"""User service with JIT provisioning."""

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.shared.checkpointing import delete_conversation_checkpoints
from app.agents.shared.memory.factory import delete_user_memory
from app.core.logging import logger
from app.integrations.clerk import (
    ClerkUserNotFoundError,
    clerk_client,
)
from app.integrations.clerk.timestamps import clerk_timestamp_to_datetime
from app.models.user import User
from app.services.conversation import conversation_service
from app.services.user.repository import user_repository


class UserService:
    """Provides user objects with JIT provisioning.

    Flow: DB (indexed clerk_id lookup) -> Clerk API (JIT create)
    """

    async def resolve_user(
        self,
        clerk_id: str,
        session: AsyncSession,
    ) -> User:
        """Resolve the current user by clerk_id, JIT-provisioning if needed.

        Args:
            clerk_id: The Clerk user ID.
            session: Database session for DB operations.

        Returns:
            The User object (attached to the current session).

        Raises:
            RuntimeError: If user cannot be provisioned from Clerk.
            UserAlreadyExistsError: A genuine (non-race) unique constraint
                conflict during provisioning — see UserRepository.create_or_get.
        """
        # 1. Look up by clerk_id (unique + indexed -> single index scan).
        #    There is deliberately no clerk_id -> user_id cache: a hit would
        #    still cost one indexed lookup, and FastAPI's per-request Depends
        #    cache already prevents repeat resolution within a request.
        user = await user_repository.get_by_clerk_id(session, clerk_id)
        if user:
            return user

        # 2. JIT: Fetch from Clerk and create in DB
        logger.info("jit_provisioning_user", clerk_id=clerk_id)

        try:
            clerk_user = await asyncio.to_thread(clerk_client.get_user, clerk_id)
        except ClerkUserNotFoundError:
            logger.error("clerk_user_not_found_during_provisioning", clerk_id=clerk_id)
            raise

        email = clerk_client.get_primary_email(clerk_user)

        if not email:
            logger.error("clerk_user_missing_email", clerk_id=clerk_id)
            raise RuntimeError(f"No email found for Clerk user {clerk_id}")

        user = await user_repository.create_or_get(
            session=session,
            clerk_id=clerk_id,
            email=email,
            first_name=clerk_user.first_name,
            last_name=clerk_user.last_name,
            avatar_url=clerk_user.image_url,
            email_verified=bool(clerk_user.primary_email_address_id),
            last_synced_at=clerk_timestamp_to_datetime(getattr(clerk_user, "updated_at", None)),
        )

        return user

    async def erase_user(
        self,
        user: User,
        session: AsyncSession,
    ) -> None:
        """Run the GDPR erasure cascade for one user.

        Shared by DELETE /api/v1/auth/me and the user.deleted webhook. The
        caller is responsible for deleting the user from Clerk — the webhook
        path must not, because a Clerk-side deletion is what produced the
        event.

        Step order is contractual. Checkpoints and memories are keyed by
        identifiers that anonymize_user() destroys, so they must be cleared
        first.

        Idempotent: on a second run the conversation list is empty, mem0
        deletion is a no-op, and the row is already anonymised.

        Args:
            user: The user to erase. Must be attached to `session`.
            session: Database session. Committed by this method.
        """
        conversation_ids = await conversation_service.soft_delete_all_user_conversations(session, user.id)
        for conv_id in conversation_ids:
            await delete_conversation_checkpoints(conv_id)

        await delete_user_memory(user.id)

        # Eagerly load conversations so anonymize_user() can iterate them
        # without a synchronous lazy load on an async session (MissingGreenlet).
        await session.refresh(user, attribute_names=["conversations"])
        user.anonymize_user()
        session.add(user)
        await session.commit()

        logger.info(
            "user_erased",
            user_id=user.id,
            conversation_count=len(conversation_ids),
        )

    async def exists_in_clerk(self, clerk_id: str) -> bool:
        """Report whether Clerk still holds this user.

        Thin wrapper so callers outside the user service do not import
        clerk_client directly (CLAUDE.md auth rule).

        The webhook create paths gate on this. A webhook payload is a
        past-tense statement and svix redelivers with backoff, so a snapshot
        taken before a deletion can land after it; Clerk is the only thing
        that can still tell the two apart once erase_user() has rewritten
        clerk_id. JIT provisioning already asks the same question implicitly,
        by holding a live JWT.

        Only the 404 is an answer. Every other Clerk error is inconclusive
        and propagates, so the delivery fails and svix retries rather than a
        row being created — or declined — on a maybe.

        Args:
            clerk_id: The Clerk user identifier.

        Returns:
            True if Clerk still holds the user, False on a 404.

        Raises:
            ClerkAuthenticationError / ClerkRateLimitError / ClerkAPIError:
                Propagated from ClerkClient.get_user.
        """
        try:
            await asyncio.to_thread(clerk_client.get_user, clerk_id)
            return True
        except ClerkUserNotFoundError:
            return False

    async def delete_user_from_clerk(self, clerk_id: str) -> None:
        """Delete a user from Clerk by clerk_id.

        Thin wrapper so callers outside the user service do not import
        clerk_client directly (CLAUDE.md auth rule).

        Args:
            clerk_id: The Clerk user identifier.

        Raises:
            ClerkAPIError / ClerkAuthenticationError: Propagated from ClerkClient.delete_user.
        """
        await asyncio.to_thread(clerk_client.delete_user, clerk_id)


user_service = UserService()
