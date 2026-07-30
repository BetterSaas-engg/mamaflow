"""Persist and query extracted items, scoped to a user."""

import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.config.settings import settings
from api.models.item import Item
from api.models.synced_message import SyncedMessage
from api.models.user import User
from api.schemas.family_event import FamilyItem


async def existing_message_ids(
    db: AsyncSession,
    user_id,
    message_ids: list[str],
) -> set[str]:
    """Which of these Gmail message ids have already been processed for this
    user. Used to skip already-synced messages BEFORE body fetch / Claude
    extraction (incremental sync) — dedup must happen before the expensive
    calls.

    A message counts as processed if EITHER it produced a persisted item OR it
    carries a `synced_messages` marker (written for zero-event mail). Querying
    both keeps pre-marker items recognized while stopping the re-extraction of
    emails that legitimately yield no events.

    A marker for a message that FAILED only counts once we've given up on it
    (attempts >= EXTRACTION_MAX_ATTEMPTS). An in-flight retry stays eligible,
    so genuine transient faults still get their retries — but a hopeless
    message stops being fetched and re-sent forever.
    """
    if not message_ids:
        return set()
    item_rows = await db.execute(
        select(Item.source_message_id).where(
            Item.user_id == user_id,
            Item.source_message_id.in_(message_ids),
            Item.deleted_at.is_(None),
        )
    )
    marker_rows = await db.execute(
        select(SyncedMessage.source_message_id).where(
            SyncedMessage.user_id == user_id,
            SyncedMessage.source_message_id.in_(message_ids),
            SyncedMessage.deleted_at.is_(None),
            or_(
                SyncedMessage.failure_kind.is_(None),  # succeeded / gate-skipped
                SyncedMessage.attempts >= settings.extraction_max_attempts,
            ),
        )
    )
    return {row[0] for row in item_rows} | {row[0] for row in marker_rows}


async def _get_marker(db: AsyncSession, user_id, message_id: str) -> SyncedMessage | None:
    result = await db.execute(
        select(SyncedMessage).where(
            SyncedMessage.user_id == user_id,
            SyncedMessage.source_message_id == message_id,
            SyncedMessage.deleted_at.is_(None),
        ).limit(1)
    )
    return result.scalar_one_or_none()


async def mark_message_synced(
    db: AsyncSession,
    user_id,
    message_id: str,
) -> None:
    """Record that a message was successfully extracted (even with zero events)
    so incremental sync never re-sends it to Claude. Idempotent per
    (user, message); call only after a successful extraction.

    A message that previously failed and later succeeds has its failure state
    cleared — success is the terminal state, not the failure count."""
    existing = await _get_marker(db, user_id, message_id)
    if existing is not None:
        if existing.failure_kind is not None:
            existing.failure_kind = None
            await db.commit()
        return
    db.add(SyncedMessage(user_id=user_id, source_message_id=message_id))
    await db.commit()


async def mark_messages_blocked(
    db: AsyncSession,
    user_id,
    message_ids: list[str],
) -> None:
    """Record that these messages were rejected by the sender blocklist, so
    they stop re-entering the per-run window.

    Without this, blocked ids were never marked and stayed "unsynced" for the
    whole 30-day query window. Because the run selects the OLDEST unsynced ids
    first, a user with more in-window blocked mail than the per-run cap had
    every batch saturated by the same blocked ids forever — real mail newer
    than them was never reached. That is the silent-drop bug this window fix
    exists to close, re-created through a different door (2026-07-28 audit).

    Deliberately the same marker table as a success: both mean "we have made a
    terminal decision about this message and never need to look again". No body
    was fetched, so this stores no content. If the blocklist itself changes,
    already-classified mail is not reconsidered — the same trade-off the D36
    gate already makes, and the blocklist is structural (D13), not a user knob.
    """
    if not message_ids:
        return
    existing = await db.execute(
        select(SyncedMessage.source_message_id).where(
            SyncedMessage.user_id == user_id,
            SyncedMessage.source_message_id.in_(message_ids),
            SyncedMessage.deleted_at.is_(None),
        )
    )
    seen = {row[0] for row in existing}
    new = [m for m in message_ids if m not in seen]
    if not new:
        return
    db.add_all(
        SyncedMessage(user_id=user_id, source_message_id=m) for m in new
    )
    await db.commit()


async def record_message_failure(
    db: AsyncSession,
    user_id,
    message_id: str,
    kind: str,
) -> int:
    """Record a failed extraction attempt; returns the new attempt count.

    kind is "permanent" (a 400/validation error — retrying cannot succeed, so
    burn the whole budget at once) or "transient" (rate limit, 5xx, DB blip —
    worth another try next sync). Without this, every failure was retried
    hourly forever at full price.
    """
    marker = await _get_marker(db, user_id, message_id)
    max_attempts = settings.extraction_max_attempts
    if marker is None:
        marker = SyncedMessage(user_id=user_id, source_message_id=message_id, attempts=0)
        db.add(marker)
    marker.attempts = max_attempts if kind == "permanent" else (marker.attempts or 0) + 1
    marker.failure_kind = kind
    marker.last_attempt_at = datetime.datetime.now(datetime.timezone.utc)
    await db.commit()
    return marker.attempts


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
    status: str | None = None,
) -> list[Item]:
    """List a user's non-deleted items, newest event first.

    Date filters compare on event_date; ISO 'YYYY-MM-DD' strings sort
    lexicographically, so range comparison is correct.
    """
    query = select(Item).where(Item.user_id == user.id, Item.deleted_at.is_(None))

    if item_type is not None:
        query = query.where(Item.item_type == item_type)
    if status is not None:
        query = query.where(Item.status == status)
    if date_from is not None:
        query = query.where(Item.event_date >= date_from)
    if date_to is not None:
        query = query.where(Item.event_date <= date_to)

    query = query.order_by(Item.event_date.is_(None), Item.event_date, Item.created_at)
    result = await db.execute(query)
    return list(result.scalars().all())
