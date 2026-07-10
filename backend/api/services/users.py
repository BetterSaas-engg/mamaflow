"""User lookup/creation for the mobile auth flow."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.user import User


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def _find_by_email(db: AsyncSession, normalized: str) -> User | None:
    result = await db.execute(select(User).where(User.email == normalized))
    return result.scalar_one_or_none()


async def get_or_create_user(db: AsyncSession, email: str) -> User:
    """Return the user for `email`, creating one if absent. Idempotent.

    A previously soft-deleted user is reactivated (deleted_at cleared) rather
    than duplicated — email is unique, and re-signing-in after account deletion
    is a fresh start (their old soft-deleted items stay hidden)."""
    normalized = normalize_email(email)

    user = await _find_by_email(db, normalized)
    if user is not None:
        if user.deleted_at is not None:
            user.deleted_at = None
            await db.commit()
            await db.refresh(user)
        return user

    user = User(email=normalized)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        # Lost a concurrent first-sign-in race on the unique email — the other
        # transaction's row is this user.
        await db.rollback()
        winner = await _find_by_email(db, normalized)
        if winner is None:  # constraint fired, so the row must exist
            raise
        return winner
    await db.refresh(user)
    return user
