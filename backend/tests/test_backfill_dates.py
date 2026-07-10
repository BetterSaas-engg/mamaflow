"""Backfill of existing items' prose event_date -> ISO (A0b)."""

from sqlalchemy import select

from api.db.backfill_dates import backfill_item_dates
from api.models.item import Item
from api.services.users import get_or_create_user


async def _add_item(db, user, event_date):
    item = Item(
        user_id=user.id, source_message_id="m", item_type="event",
        event_title="Soccer", event_date=event_date,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def test_backfill_rewrites_prose_date_to_iso(db):
    user = await get_or_create_user(db, "p@x.com")
    item = await _add_item(db, user, "July 5th (Saturday) 10:00 AM")

    fixed = await backfill_item_dates(db)

    await db.refresh(item)
    # created_at is ~now (2026) -> the yearless date resolves to that year.
    assert item.event_date == f"{item.created_at.year}-07-05"
    assert fixed == 1


async def test_backfill_leaves_iso_and_unparseable_untouched(db):
    user = await get_or_create_user(db, "p@x.com")
    iso = await _add_item(db, user, "2026-07-05")
    bad = await _add_item(db, user, "sometime soon")

    fixed = await backfill_item_dates(db)

    await db.refresh(iso)
    await db.refresh(bad)
    assert iso.event_date == "2026-07-05"   # already ISO -> untouched
    assert bad.event_date == "sometime soon"  # unparseable -> untouched
    assert fixed == 0  # neither item was a fixable prose date


async def test_backfill_is_idempotent(db):
    user = await get_or_create_user(db, "p@x.com")
    await _add_item(db, user, "July 5th (Saturday)")

    first = await backfill_item_dates(db)
    second = await backfill_item_dates(db)

    assert first == 1
    assert second == 0
