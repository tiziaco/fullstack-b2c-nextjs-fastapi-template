"""User repository for database operations."""

from datetime import (
    UTC,
    datetime,
)
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logging import logger
from app.models.user import User
from app.services.user.exceptions import UserAlreadyExistsError


class UserRepository:
    """Repository for user database operations."""

    @staticmethod
    async def get_by_id(session: AsyncSession, user_id: str) -> Optional[User]:
        """Get a user by internal ID."""
        return await session.get(User, user_id)

    @staticmethod
    async def get_by_clerk_id(session: AsyncSession, clerk_id: str) -> Optional[User]:
        """Get a user by Clerk ID (e.g. "user_2abc123xyz")."""
        statement = select(User).where(User.clerk_id == clerk_id)
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_email(session: AsyncSession, email: str) -> Optional[User]:
        """Get a user by email."""
        statement = select(User).where(User.email == email)
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    @staticmethod
    async def create(
        session: AsyncSession,
        clerk_id: str,
        email: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        email_verified: bool = False,
        last_synced_at: Optional[datetime] = None,
    ) -> User:
        """Create a new user from Clerk data.

        `last_synced_at` is Clerk's own clock, read by the webhook ordering
        guard; the JIT path has no Clerk event to draw one from.
        """
        user = User(
            clerk_id=clerk_id,
            email=email,
            first_name=first_name,
            last_name=last_name,
            avatar_url=avatar_url,
            email_verified=email_verified,
            # Clerk's clock when we have it. Passing None explicitly would
            # bypass the field default, so fall back here.
            last_synced_at=last_synced_at or datetime.now(UTC),
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)

        logger.info("user_created", user_id=user.id, clerk_id=clerk_id)
        return user

    @staticmethod
    async def create_or_get(
        session: AsyncSession,
        clerk_id: str,
        email: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        email_verified: bool = False,
        last_synced_at: Optional[datetime] = None,
    ) -> User:
        """Create a user, or return the existing one if a concurrent request won the race.

        Two requests JIT-provisioning the same clerk_id can race; the loser's
        insert hits the unique constraint. Roll back and return the winner's row
        rather than surfacing a conflict.

        Raises UserAlreadyExistsError when the re-fetch by clerk_id finds
        nothing: the IntegrityError was some other collision (an email already
        held by a different clerk_id), so it is a genuine conflict.
        """
        try:
            return await UserRepository.create(
                session=session,
                clerk_id=clerk_id,
                email=email,
                first_name=first_name,
                last_name=last_name,
                avatar_url=avatar_url,
                email_verified=email_verified,
                last_synced_at=last_synced_at,
            )
        except IntegrityError:
            await session.rollback()
            logger.info("jit_provisioning_race_resolved", clerk_id=clerk_id)
            user = await UserRepository.get_by_clerk_id(session, clerk_id)
            if not user:
                raise UserAlreadyExistsError(f"Failed to provision user {clerk_id}")
            return user

    @staticmethod
    async def update_from_clerk(
        session: AsyncSession,
        user: User,
        email: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        email_verified: Optional[bool] = None,
        last_synced_at: Optional[datetime] = None,
    ) -> User:
        """Update a user's profile from Clerk data. None means "leave alone"."""
        now = datetime.now(UTC)
        if email is not None:
            user.email = email
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name
        if avatar_url is not None:
            user.avatar_url = avatar_url
        if email_verified is not None:
            user.email_verified = email_verified
        user.updated_at = now
        user.last_synced_at = last_synced_at or now

        session.add(user)
        await session.flush()
        await session.refresh(user)

        logger.info("user_updated", user_id=user.id, clerk_id=user.clerk_id)
        return user

    @staticmethod
    async def delete(session: AsyncSession, user_id: str) -> bool:
        """Delete a user by internal ID. False if there is no such user."""
        user = await session.get(User, user_id)
        if not user:
            return False

        await session.delete(user)
        logger.info("user_deleted", user_id=user_id)
        return True


user_repository = UserRepository()
