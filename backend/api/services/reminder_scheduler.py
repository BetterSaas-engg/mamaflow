"""Evening-before reminder tick + APScheduler wiring. reminder_tick is testable
independently of the scheduler; start/stop_scheduler wire it into the app
lifespan (inert unless push_sender is configured)."""

import datetime
import logging
from zoneinfo import ZoneInfo

from sqlalchemy import update

from api.config.settings import settings
from api.models.device import Device
from api.services import push_sender, reminders

_log = logging.getLogger(__name__)
_scheduler = None


async def _prune(db, dead: list[str]) -> None:
    if not dead:
        return
    await db.execute(
        update(Device)
        .where(Device.fcm_token.in_(dead), Device.deleted_at.is_(None))
        .values(deleted_at=datetime.datetime.now(datetime.UTC))
    )
    await db.commit()


async def reminder_tick(session_factory, *, now: datetime.datetime | None = None) -> None:
    """Send the evening-before digest to eligible users. No-op outside the
    reminder hour. Per-user failures are caught so one bad user can't abort the
    tick; last_reminder_date advances only on a successful send (daily dedup)."""
    now = now or datetime.datetime.now(datetime.UTC)
    local = now.astimezone(ZoneInfo(settings.reminder_tz))
    if local.hour != settings.reminder_hour:
        return
    today = local.date()
    tomorrow = (today + datetime.timedelta(days=1)).isoformat()

    async with session_factory() as db:
        for user in await reminders.users_with_devices(db):
            if user.last_reminder_date == today:
                continue
            try:
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
                await db.rollback()
