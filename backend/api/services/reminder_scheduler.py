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


def _make_scheduler():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    return AsyncIOScheduler()


def start_scheduler() -> None:
    """Start the hourly jobs. Each registers under its own condition —
    reminders need Firebase, auto-sync needs its knob — and the scheduler
    only starts when at least one job is wanted (inert otherwise)."""
    global _scheduler
    want_reminders = push_sender.is_configured()
    want_auto_sync = settings.auto_sync_enabled
    if not (want_reminders or want_auto_sync):
        _log.info("scheduler: no jobs wanted — not started")
        return
    from apscheduler.triggers.cron import CronTrigger

    from api.db.session import get_session_factory
    from api.services.auto_sync import auto_sync_tick

    session_factory = get_session_factory()
    _scheduler = _make_scheduler()
    if want_reminders:
        _scheduler.add_job(
            reminder_tick,
            CronTrigger(minute=0),
            kwargs={"session_factory": session_factory},
            id="reminder_tick",
            replace_existing=True,
        )
    else:
        _log.info("reminders: FIREBASE_CREDENTIALS_JSON unset — reminder job not registered")
    if want_auto_sync:
        _scheduler.add_job(
            auto_sync_tick,
            CronTrigger(minute=30),
            kwargs={"session_factory": session_factory},
            id="auto_sync_tick",
            replace_existing=True,
        )
    _scheduler.start()
    _log.info(
        "scheduler started (reminders=%s, auto_sync=%s)", want_reminders, want_auto_sync
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
