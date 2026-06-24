"""User lookup/creation for the mobile auth flow."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.user import User


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def get_or_create_user(db: AsyncSession, email: str) -> User:
    """Return the user for `email`, creating one if absent. Idempotent."""
    normalized = normalize_email(email)

    result = await db.execute(
        select(User).where(User.email == normalized, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    user = User(email=normalized)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
