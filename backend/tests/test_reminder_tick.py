import datetime

from sqlalchemy import select

from api.config.settings import settings
from api.models.device import Device
from api.schemas.family_event import FamilyItem
from api.services import reminder_scheduler
from api.services.items import persist_items
from api.services.users import get_or_create_user

# now = 18:00 UTC on 2026-07-06 -> tomorrow = 2026-07-07 (with reminder_tz=UTC).
_NOW = datetime.datetime(2026, 7, 6, 18, 0, tzinfo=datetime.UTC)


async def _seed(db, email="p@x.com", token="tok", date="2026-07-07"):
    user = await get_or_create_user(db, email)
    db.add(Device(user_id=user.id, fcm_token=token, platform="ios"))
    await persist_items(db, user, "m", [FamilyItem(item_type="event", event_title="Soccer", date=date)])
    await db.commit()
    return user


async def test_tick_sends_then_dedups(db, session_factory, monkeypatch):
    monkeypatch.setattr(settings, "reminder_tz", "UTC")
    monkeypatch.setattr(settings, "reminder_hour", 18)
    user = await _seed(db)

    sent = []
    async def fake_send(tokens, title, body):
        sent.append((tokens, title, body))
        return []
    monkeypatch.setattr(reminder_scheduler.push_sender, "send_digest", fake_send)

    await reminder_scheduler.reminder_tick(session_factory, now=_NOW)
    assert len(sent) == 1
    assert sent[0][0] == ["tok"]
    await db.refresh(user)
    assert user.last_reminder_date == datetime.date(2026, 7, 6)

    # Second tick the same day -> dedup, no send.
    await reminder_scheduler.reminder_tick(session_factory, now=_NOW)
    assert len(sent) == 1


async def test_tick_offhour_is_noop(db, session_factory, monkeypatch):
    monkeypatch.setattr(settings, "reminder_tz", "UTC")
    monkeypatch.setattr(settings, "reminder_hour", 18)
    await _seed(db)
    sent = []
    monkeypatch.setattr(reminder_scheduler.push_sender, "send_digest",
                        lambda *a, **k: sent.append(1))
    await reminder_scheduler.reminder_tick(
        session_factory, now=datetime.datetime(2026, 7, 6, 9, 0, tzinfo=datetime.UTC)
    )
    assert sent == []


async def test_tick_prunes_dead_tokens(db, session_factory, monkeypatch):
    monkeypatch.setattr(settings, "reminder_tz", "UTC")
    monkeypatch.setattr(settings, "reminder_hour", 18)
    user = await _seed(db, token="dead-tok")

    async def fake_send(tokens, title, body):
        return list(tokens)  # all dead
    monkeypatch.setattr(reminder_scheduler.push_sender, "send_digest", fake_send)

    await reminder_scheduler.reminder_tick(session_factory, now=_NOW)

    devices = (await db.execute(select(Device).where(Device.user_id == user.id))).scalars().all()
    assert all(d.deleted_at is not None for d in devices)  # dead token soft-deleted


async def test_tick_skips_user_without_tomorrow_events(db, session_factory, monkeypatch):
    monkeypatch.setattr(settings, "reminder_tz", "UTC")
    monkeypatch.setattr(settings, "reminder_hour", 18)
    user = await _seed(db, date="2026-12-31")  # not tomorrow
    sent = []
    monkeypatch.setattr(reminder_scheduler.push_sender, "send_digest",
                        lambda *a, **k: sent.append(1))
    await reminder_scheduler.reminder_tick(session_factory, now=_NOW)
    assert sent == []
    await db.refresh(user)
    assert user.last_reminder_date is None  # not advanced when nothing sent
