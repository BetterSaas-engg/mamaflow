"""Tests for item persistence + listing service (Phase B)."""

from api.schemas.family_event import FamilyItem
from api.services.items import list_items, persist_items
from api.services.users import get_or_create_user


def _event(title, date=None, item_type="event"):
    return FamilyItem(item_type=item_type, event_title=title, date=date)


async def test_persist_inserts_rows_scoped_to_user(db):
    user = await get_or_create_user(db, "parent@example.com")

    saved = await persist_items(db, user, "msg1", [_event("Soccer", "2026-06-20")])

    assert len(saved) == 1
    assert saved[0].user_id == user.id
    assert saved[0].event_title == "Soccer"
    assert saved[0].status == "open"


async def test_persist_is_idempotent_per_message(db):
    user = await get_or_create_user(db, "parent@example.com")
    items = [_event("Soccer", "2026-06-20")]

    await persist_items(db, user, "msg1", items)
    second = await persist_items(db, user, "msg1", items)  # same message re-synced

    assert second == []  # nothing re-inserted
    all_items = await list_items(db, user)
    assert len(all_items) == 1


async def test_list_is_scoped_to_the_user(db):
    alice = await get_or_create_user(db, "alice@example.com")
    bob = await get_or_create_user(db, "bob@example.com")
    await persist_items(db, alice, "m1", [_event("Alice event", "2026-06-20")])
    await persist_items(db, bob, "m2", [_event("Bob event", "2026-06-20")])

    alice_items = await list_items(db, alice)

    assert len(alice_items) == 1
    assert alice_items[0].event_title == "Alice event"


async def test_list_filters_by_date_range_and_type(db):
    user = await get_or_create_user(db, "parent@example.com")
    await persist_items(db, user, "m1", [
        _event("May", "2026-05-10"),
        _event("June", "2026-06-15"),
        _event("July", "2026-07-15"),
    ])
    await persist_items(db, user, "m2", [_event("Todo", None, item_type="action")])

    june_only = await list_items(db, user, date_from="2026-06-01", date_to="2026-06-30")
    assert {i.event_title for i in june_only} == {"June"}

    actions = await list_items(db, user, item_type="action")
    assert {i.event_title for i in actions} == {"Todo"}
