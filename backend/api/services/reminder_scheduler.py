"""Evening-before reminder tick + APScheduler wiring. reminder_tick is testable
independently of the scheduler; start/stop_scheduler wire it into the app
lifespan (inert unless push_sender is configured)."""

import datetime
import logging
from zoneinfo import ZoneInfo

from sqlalchemy import update

from api.config.settings import settings
from api.models.device import Device
from api.models.user import User
from api.services import push_sender, reminders

_log = logging.getLogger(__name__)
_scheduler = None


async def _prune(db, dead: list[str]) -> None:
    """Soft-delete dead FCM tokens. Does NOT commit — the caller commits once."""
    if not dead:
        return
    await db.execute(
        update(Device)
        .where(Device.fcm_token.in_(dead), Device.deleted_at.is_(None))
        .values(deleted_at=datetime.datetime.now(datetime.UTC))
    )


async def reminder_tick(session_factory, *, now: datetime.datetime | None = None) -> None:
    """Send the evening-before digest to eligible users. No-op outside the
    reminder hour. Each user is processed in its OWN session so one user's
    failure (and rollback) can't affect the others; last_reminder_date advances
    only on a successful send (daily dedup)."""
    now = now or datetime.datetime.now(datetime.UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.UTC)  # naive -> treat as UTC
    local = now.astimezone(ZoneInfo(settings.reminder_tz))
    if local.hour != settings.reminder_hour:
        return
    today = local.date()
    tomorrow = (today + datetime.timedelta(days=1)).isoformat()

    async with session_factory() as db:
        user_ids = [user.id for user in await reminders.users_with_devices(db)]

    for user_id in user_ids:
        try:
            async with session_factory() as db:
                user = await db.get(User, user_id)
                if user is None or user.deleted_at is not None:
                    continue
                if user.last_reminder_date == today:
                    continue
                events = await reminders.tomorrow_events(db, user, tomorrow)
                if not events:
                    continue
                tokens = await reminders.device_tokens(db, user)
                title, body = reminders.format_digest(events)
                dead = await push_sender.send_digest(tokens, title, body)
                await _prune(db, dead)
                user.last_reminder_date = today
                await db.commit()
        except Exception as exc:
            _log.warning("reminder tick failed for a user (%s)", type(exc).__name__)
