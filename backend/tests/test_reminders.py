import datetime
from types import SimpleNamespace

from api.models.device import Device
from api.schemas.family_event import FamilyItem
from api.services import reminders
from api.services.items import persist_items
from api.services.users import get_or_create_user


async def test_tomorrow_events_selects_only_open_dated_events(db):
    user = await get_or_create_user(db, "p@x.com")
    await persist_items(db, user, "m1", [
        FamilyItem(item_type="event", event_title="Soccer", date="2026-07-07"),
        FamilyItem(item_type="event", event_title="Later", date="2026-07-09"),   # wrong date
        FamilyItem(item_type="action", action_required="RSVP"),                   # dateless action
    ])
    await db.commit()

    events = await reminders.tomorrow_events(db, user, "2026-07-07")

    assert [e.event_title for e in events] == ["Soccer"]


async def test_tomorrow_events_sorted_chronologically_not_lexicographically(db):
    """event_time is a free-form string; a lexicographic sort puts '10:00 AM'
    before '9:00 AM'. The digest must list events in wall-clock order, with
    untimed events last."""
    user = await get_or_create_user(db, "t@x.com")
    await persist_items(db, user, "mt", [
        FamilyItem(item_type="event", event_title="Untimed", date="2026-07-07"),
        FamilyItem(item_type="event", event_title="Recital", date="2026-07-07", time="2:30 PM"),
        FamilyItem(item_type="event", event_title="Dentist", date="2026-07-07", time="10:00 AM"),
        FamilyItem(item_type="event", event_title="Drop-off", date="2026-07-07", time="9:00 AM"),
        FamilyItem(item_type="event", event_title="Dinner", date="2026-07-07", time="18:30"),
    ])
    await db.commit()

    events = await reminders.tomorrow_events(db, user, "2026-07-07")

    assert [e.event_title for e in events] == [
        "Drop-off", "Dentist", "Recital", "Dinner", "Untimed",
    ]


def test_time_sort_key_handles_free_form_values():
    key = reminders._time_key
    assert key("9:00 AM") < key("10:00 AM") < key("2:30 PM")
    assert key("2:30 PM") < key("18:30")  # 24h format parsed too
    assert key("9AM") < key("noon-ish")   # unparseable sorts last...
    assert key("noon-ish") == key(None)   # ...alongside missing times


async def test_tomorrow_events_excludes_done_and_other_users(db):
    a = await get_or_create_user(db, "a@x.com")
    b = await get_or_create_user(db, "b@x.com")
    [a_item] = await persist_items(db, a, "ma", [FamilyItem(item_type="event", event_title="A", date="2026-07-07")])
    await persist_items(db, b, "mb", [FamilyItem(item_type="event", event_title="B", date="2026-07-07")])
    a_item.status = "done"
    await db.commit()

    assert await reminders.tomorrow_events(db, a, "2026-07-07") == []  # a's is done
    assert [e.event_title for e in await reminders.tomorrow_events(db, b, "2026-07-07")] == ["B"]


async def test_users_with_devices_and_tokens(db):
    a = await get_or_create_user(db, "a@x.com")
    await get_or_create_user(db, "nodevice@x.com")
    db.add(Device(user_id=a.id, fcm_token="tok-1", platform="ios"))
    db.add(Device(user_id=a.id, fcm_token="tok-2", platform="android"))
    await db.commit()

    users = await reminders.users_with_devices(db)
    assert [u.email for u in users] == ["a@x.com"]  # distinct, only users with devices
    assert sorted(await reminders.device_tokens(db, a)) == ["tok-1", "tok-2"]


def test_format_digest_caps_and_includes_time():
    items = [SimpleNamespace(event_title=f"E{i}", event_time="10:00 AM" if i == 0 else None) for i in range(7)]
    title, body = reminders.format_digest(items)
    assert title == "Tomorrow's schedule"
    assert body.startswith("E0 10:00 AM · E1 · ")
    assert body.endswith("and 2 more")  # 5 shown + "and 2 more"


async def test_soft_deleted_device_excluded(db):
    user = await get_or_create_user(db, "sd@x.com")
    live = Device(user_id=user.id, fcm_token="live-tok", platform="ios")
    dead = Device(
        user_id=user.id, fcm_token="dead-tok", platform="android",
        deleted_at=datetime.datetime.now(datetime.UTC),
    )
    db.add(live)
    db.add(dead)
    await db.commit()

    # device_tokens returns only the live token; the user still appears once.
    assert await reminders.device_tokens(db, user) == ["live-tok"]
    users = await reminders.users_with_devices(db)
    assert [u.email for u in users] == ["sd@x.com"]


async def test_user_with_only_soft_deleted_device_excluded(db):
    user = await get_or_create_user(db, "gone@x.com")
    db.add(Device(
        user_id=user.id, fcm_token="only-dead", platform="ios",
        deleted_at=datetime.datetime.now(datetime.UTC),
    ))
    await db.commit()

    # No live devices -> user is not selected and has no tokens.
    assert await reminders.device_tokens(db, user) == []
    assert user.email not in {u.email for u in await reminders.users_with_devices(db)}
