"""Selecting + formatting the evening-before reminder digest. Pure DB reads +
string formatting — no push/network here (see push_sender)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.device import Device
from api.models.item import Item
from api.models.user import User

_MAX_LISTED = 5


async def users_with_devices(db: AsyncSession) -> list[User]:
    rows = await db.execute(
        select(User)
        .join(Device, Device.user_id == User.id)
        .where(User.deleted_at.is_(None), Device.deleted_at.is_(None))
        .distinct()
    )
    return list(rows.scalars().all())


async def device_tokens(db: AsyncSession, user: User) -> list[str]:
    rows = await db.execute(
        select(Device.fcm_token).where(
            Device.user_id == user.id, Device.deleted_at.is_(None)
        )
    )
    return list(rows.scalars().all())


async def tomorrow_events(db: AsyncSession, user: User, target_date: str) -> list[Item]:
    rows = await db.execute(
        select(Item)
        .where(
            Item.user_id == user.id,
            Item.deleted_at.is_(None),
            Item.status == "open",
            Item.item_type == "event",
            Item.event_date == target_date,
        )
        .order_by(Item.event_time)
    )
    return list(rows.scalars().all())


def format_digest(items) -> tuple[str, str]:
    parts: list[str] = []
    for item in items[:_MAX_LISTED]:
        title = item.event_title or "Event"
        parts.append(f"{title} {item.event_time}" if item.event_time else title)
    body = " · ".join(parts)
    extra = len(items) - _MAX_LISTED
    if extra > 0:
        body += f" · and {extra} more"
    return "Tomorrow's schedule", body
