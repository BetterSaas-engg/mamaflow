"""User lookup/creation for the mobile auth flow."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.user import User


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def get_or_create_user(db: AsyncSession, email: str) -> User:
    """Return the user for `email`, creating one if absent. Idempotent.

    A previously soft-deleted user is reactivated (deleted_at cleared) rather
    than duplicated — email is unique, and re-signing-in after account deletion
    is a fresh start (their old soft-deleted items stay hidden)."""
    normalized = normalize_email(email)

    result = await db.execute(select(User).where(User.email == normalized))
    user = result.scalar_one_or_none()
    if user is not None:
        if user.deleted_at is not None:
            user.deleted_at = None
            await db.commit()
            await db.refresh(user)
        return user

    user = User(email=normalized)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
