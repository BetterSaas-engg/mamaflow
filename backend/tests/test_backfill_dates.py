"""Backfill of existing items' prose event_date -> ISO (A0b).

The year for a yearless prose date comes from the ITEM'S created_at, not from
today — a backfill run months later must not shunt old items into the future.
So these tests pin created_at explicitly. The original version used "now" and
asserted the current year, which quietly became a time bomb: it passed until
the real date drifted more than 30 days past the prose date (2026-08-05), then
started failing on a branch that had nothing to do with dates.
"""

import datetime

from sqlalchemy import select

from api.db.backfill_dates import backfill_item_dates
from api.models.item import Item
from api.services.users import get_or_create_user


async def _add_item(db, user, event_date, created_at=None):
    item = Item(
        user_id=user.id, source_message_id="m", item_type="event",
        event_title="Soccer", event_date=event_date,
    )
    if created_at is not None:
        item.created_at = created_at
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def test_backfill_rewrites_prose_date_to_iso(db):
    """A yearless date takes the year of the item it belongs to."""
    user = await get_or_create_user(db, "p@x.com")
    item = await _add_item(
        db,
        user,
        "July 5th (Saturday) 10:00 AM",
        created_at=datetime.datetime(2026, 6, 20, tzinfo=datetime.UTC),
    )

    fixed = await backfill_item_dates(db)

    await db.refresh(item)
    assert item.event_date == "2026-07-05"
    assert fixed == 1


async def test_a_yearless_date_well_before_the_email_means_next_year(db):
    """The rule normalize_item_date documents: more than 30 days before the
    email was sent means the NEXT occurrence — a December email about
    "January 5" is next January, not ten months ago. Pinned here because it is
    the branch the old test hit by accident once the calendar moved."""
    user = await get_or_create_user(db, "p@x.com")
    item = await _add_item(
        db,
        user,
        "January 5th",
        created_at=datetime.datetime(2026, 12, 20, tzinfo=datetime.UTC),
    )

    fixed = await backfill_item_dates(db)

    await db.refresh(item)
    assert item.event_date == "2027-01-05"
    assert fixed == 1


async def test_backfill_is_stable_whenever_it_runs(db):
    """Running the backfill later must not move an item's date. This is the
    property the old test's use of "now" quietly broke."""
    user = await get_or_create_user(db, "p@x.com")
    item = await _add_item(
        db,
        user,
        "July 5th",
        created_at=datetime.datetime(2026, 6, 20, tzinfo=datetime.UTC),
    )

    await backfill_item_dates(db)
    await db.refresh(item)
    first = item.event_date
    # Idempotent: a second pass is a no-op, whatever today's date is.
    assert await backfill_item_dates(db) == 0
    await db.refresh(item)

    assert item.event_date == first == "2026-07-05"


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
