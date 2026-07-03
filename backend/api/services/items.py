"""Persist and query extracted items, scoped to a user."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.item import Item
from api.models.user import User
from api.schemas.family_event import FamilyItem


async def persist_items(
    db: AsyncSession,
    user: User,
    message_id: str,
    items: list[FamilyItem],
) -> list[Item]:
    """Store extracted items for a message. Idempotent per (user, message):
    if anything is already stored for that message, do nothing (the message
    was already synced) so user status changes are never clobbered.
    """
    existing = await db.execute(
        select(Item.id).where(
            Item.user_id == user.id,
            Item.source_message_id == message_id,
            Item.deleted_at.is_(None),
        ).limit(1)
    )
    if existing.first() is not None:
        return []

    rows = [
        Item(
            user_id=user.id,
            item_type=item.item_type,
            event_title=item.event_title,
            action_required=item.action_required,
            event_date=item.date,
            event_time=item.time,
            location=item.location,
            child_name=item.child_name,
            event_type=item.event_type,
            source_sender=item.source_sender,
            source_email_link=item.source_email_link,
            source_message_id=message_id,
        )
        for item in items
    ]
    db.add_all(rows)
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return rows


async def list_items(
    db: AsyncSession,
    user: User,
    date_from: str | None = None,
    date_to: str | None = None,
    item_type: str | None = None,
) -> list[Item]:
    """List a user's non-deleted items, newest event first.

    Date filters compare on event_date; ISO 'YYYY-MM-DD' strings sort
    lexicographically, so range comparison is correct.
    """
    query = select(Item).where(Item.user_id == user.id, Item.deleted_at.is_(None))

    if item_type is not None:
        query = query.where(Item.item_type == item_type)
    if date_from is not None:
        query = query.where(Item.event_date >= date_from)
    if date_to is not None:
        query = query.where(Item.event_date <= date_to)

    query = query.order_by(Item.event_date.is_(None), Item.event_date, Item.created_at)
    result = await db.execute(query)
    return list(result.scalars().all())
