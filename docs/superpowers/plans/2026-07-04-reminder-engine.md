# Reminder Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send each user an evening-before push digest of tomorrow's events — fully built + tested but inert until a Firebase service account is configured.

**Architecture:** A `firebase-admin` push sender (inert without creds, prunes dead tokens), a pure reminder-selection/formatter module, and an APScheduler hourly job (started in the FastAPI lifespan) whose `reminder_tick` selects tomorrow's open events per user and sends the digest with per-user daily dedup. One migration adds `users.last_reminder_date`.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Pydantic v2 + Alembic; new deps `firebase-admin`, `apscheduler`.

**Spec:** `docs/superpowers/specs/2026-07-04-reminder-engine-design.md`

## Global Constraints

- The engine is **inert unless `FIREBASE_CREDENTIALS_JSON` is set** — the sender no-ops and the scheduler job is not started. The app must run exactly as today when unset.
- The Firebase service-account JSON is a **credential**: env only, never the DB (D4). No token value or digest text is ever logged (types/counts only).
- Reminders target **open, dated, event-type** items whose `event_date == tomorrow` in `REMINDER_TZ`; done/dismissed and dateless items are excluded. Every query is scoped by `user_id` + `deleted_at IS NULL`.
- Dedup: `users.last_reminder_date` is advanced **only on a successful send**; the `!= today` guard makes repeat/restart ticks in the same reminder hour a no-op.
- Config defaults (verbatim): `REMINDER_TZ=America/Toronto`, `REMINDER_HOUR=18`.
- Firewall (D19): the digest goes only to the user's own device via FCM — no content to the ad layer, no ad surface added.
- Backend: run from `backend/`, tests `./.venv/bin/python -m pytest -q` (venv python, never system). `firebase-admin` and the scheduler are **mocked in tests — never live**.
- Migrations are applied by the **user** against Railway (Claude can't write the shared DB); the test DB builds tables from the models, so the migration is authored + validated offline.
- TDD every task. Commit after each (Conventional Commits; end each body with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`).

---

### Task 1: Config + `users.last_reminder_date` + migration

**Files:**
- Modify: `backend/api/config/settings.py`
- Modify: `backend/api/models/user.py`
- Create: `backend/alembic/versions/d4e3f2a1b0c9_add_users_last_reminder_date.py`
- Test: `backend/tests/test_reminder_config.py`

**Interfaces:**
- Produces: `settings.firebase_credentials_json: str`, `settings.reminder_tz: str`, `settings.reminder_hour: int`; `User.last_reminder_date: datetime.date | None`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_reminder_config.py`:

```python
import datetime

from api.config.settings import settings
from api.models.user import User
from api.services.users import get_or_create_user


def test_reminder_settings_defaults():
    assert settings.reminder_tz == "America/Toronto"
    assert settings.reminder_hour == 18
    assert settings.firebase_credentials_json == ""


async def test_user_last_reminder_date_roundtrips(db):
    user = await get_or_create_user(db, "p@x.com")
    user.last_reminder_date = datetime.date(2026, 7, 6)
    await db.commit()
    await db.refresh(user)
    assert user.last_reminder_date == datetime.date(2026, 7, 6)
    # default is None for a fresh user
    other = await get_or_create_user(db, "q@x.com")
    assert other.last_reminder_date is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_reminder_config.py -q`
Expected: FAIL — settings lack the fields; `User` has no `last_reminder_date`.

- [ ] **Step 3: Add the settings**

In `backend/api/config/settings.py`, add inside the `Settings` class (near `sync_cooldown_seconds`, before `model_config`):

```python
    # Push reminders (Track B). Inert unless firebase_credentials_json is set
    # (the FCM service-account JSON — a credential, env only, never the DB).
    firebase_credentials_json: str = ""
    reminder_tz: str = "America/Toronto"
    reminder_hour: int = 18
```

- [ ] **Step 4: Add the model column**

In `backend/api/models/user.py`, add the import and column:

```python
import datetime

from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(unique=True, nullable=False, index=True)
    # Last date (in REMINDER_TZ) a reminder digest was sent — daily dedup.
    last_reminder_date: Mapped[datetime.date | None] = mapped_column(nullable=True)
```

- [ ] **Step 5: Write the migration**

Create `backend/alembic/versions/d4e3f2a1b0c9_add_users_last_reminder_date.py`:

```python
"""add users.last_reminder_date

Revision ID: d4e3f2a1b0c9
Revises: c3d2e1f0a9b8
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e3f2a1b0c9"
down_revision = "c3d2e1f0a9b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_reminder_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_reminder_date")
```

- [ ] **Step 6: Run tests + full suite**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_reminder_config.py -q && ./.venv/bin/python -m pytest -q`
Expected: PASS; full suite green (the test DB builds the new column from the model).

- [ ] **Step 7: Commit**

```bash
git add backend/api/config/settings.py backend/api/models/user.py backend/alembic/versions/d4e3f2a1b0c9_add_users_last_reminder_date.py backend/tests/test_reminder_config.py
git commit -m "feat(backend): reminder config + users.last_reminder_date (+ migration)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Push sender (firebase-admin, inert without creds)

**Files:**
- Create: `backend/api/services/push_sender.py`
- Test: `backend/tests/test_push_sender.py`

**Interfaces:**
- Consumes: `settings.firebase_credentials_json`.
- Produces:
  - `is_configured() -> bool`.
  - `dead_tokens_from_responses(tokens, responses) -> list[str]` (pure: tokens whose send failed with a permanent token error).
  - `async send_digest(tokens: list[str], title: str, body: str) -> list[str]` — sends a multicast, returns dead tokens; returns `[]` (no firebase call) when unconfigured or `tokens` is empty; catches + sanitized-logs any firebase error.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_push_sender.py`:

```python
from types import SimpleNamespace

from api.config.settings import settings
from api.services import push_sender


def test_is_configured_reflects_settings(monkeypatch):
    monkeypatch.setattr(settings, "firebase_credentials_json", "")
    assert push_sender.is_configured() is False
    monkeypatch.setattr(settings, "firebase_credentials_json", '{"x": 1}')
    assert push_sender.is_configured() is True


def test_dead_tokens_from_responses():
    class UnregisteredError(Exception):
        pass

    responses = [
        SimpleNamespace(success=True, exception=None),
        SimpleNamespace(success=False, exception=UnregisteredError()),
        SimpleNamespace(success=False, exception=ValueError("transient")),
    ]
    dead = push_sender.dead_tokens_from_responses(["a", "b", "c"], responses)
    assert dead == ["b"]  # only the permanent token error is pruned


async def test_send_digest_noop_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "firebase_credentials_json", "")

    def boom(*a, **k):
        raise AssertionError("firebase must not be touched when unconfigured")

    monkeypatch.setattr(push_sender, "_send_sync", boom)
    assert await push_sender.send_digest(["tok"], "t", "b") == []


async def test_send_digest_noop_on_empty_tokens(monkeypatch):
    monkeypatch.setattr(settings, "firebase_credentials_json", '{"x": 1}')
    assert await push_sender.send_digest([], "t", "b") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_push_sender.py -q`
Expected: FAIL — `api.services.push_sender` doesn't exist.

- [ ] **Step 3: Implement the sender**

Create `backend/api/services/push_sender.py`:

```python
"""FCM push sender (firebase-admin, HTTP v1). Inert unless a Firebase
service-account JSON is configured (env only, never the DB, D4). Never logs a
token value or the digest text."""

import asyncio
import json
import logging

from api.config.settings import settings

_log = logging.getLogger(__name__)
_app = None  # firebase_admin app singleton (lazy)

# FCM errors that mean the token is permanently invalid -> prune the device.
_DEAD_ERROR_TYPES = {"UnregisteredError", "SenderIdMismatchError"}


def is_configured() -> bool:
    return bool(settings.firebase_credentials_json)


def dead_tokens_from_responses(tokens: list[str], responses) -> list[str]:
    """Tokens whose send failed with a permanent token error."""
    dead: list[str] = []
    for token, response in zip(tokens, responses):
        if not getattr(response, "success", False):
            if type(getattr(response, "exception", None)).__name__ in _DEAD_ERROR_TYPES:
                dead.append(token)
    return dead


def _send_sync(tokens: list[str], title: str, body: str) -> list[str]:
    global _app
    import firebase_admin
    from firebase_admin import credentials, messaging

    if _app is None:
        _app = firebase_admin.initialize_app(
            credentials.Certificate(json.loads(settings.firebase_credentials_json))
        )
    response = messaging.send_each_for_multicast(
        messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title, body=body),
        )
    )
    return dead_tokens_from_responses(tokens, response.responses)


async def send_digest(tokens: list[str], title: str, body: str) -> list[str]:
    """Send a digest to the tokens; return the dead ones (to prune). No-op
    (returns []) when unconfigured or tokens is empty. Blocking firebase runs
    off the event loop; any failure is logged sanitized, never raised."""
    if not is_configured() or not tokens:
        return []
    try:
        return await asyncio.to_thread(_send_sync, tokens, title, body)
    except Exception as exc:
        _log.warning("push send failed (%s)", type(exc).__name__)
        return []
```

- [ ] **Step 4: Run tests + full suite**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_push_sender.py -q && ./.venv/bin/python -m pytest -q`
Expected: PASS; full suite green.

- [ ] **Step 5: Commit**

```bash
git add backend/api/services/push_sender.py backend/tests/test_push_sender.py
git commit -m "feat(backend): FCM push sender (firebase-admin, inert without creds)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Reminder selection + digest formatting

**Files:**
- Create: `backend/api/services/reminders.py`
- Test: `backend/tests/test_reminders.py`

**Interfaces:**
- Consumes: `User`, `Device`, `Item` models.
- Produces:
  - `async users_with_devices(db) -> list[User]` (users with ≥1 non-deleted device).
  - `async device_tokens(db, user) -> list[str]`.
  - `async tomorrow_events(db, user, target_date: str) -> list[Item]` (open, event-type, `event_date == target_date`, scoped to user, non-deleted; ordered by `event_time`).
  - `format_digest(items) -> tuple[str, str]` (title, body; caps at 5 + "and N more").

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_reminders.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_reminders.py -q`
Expected: FAIL — `api.services.reminders` doesn't exist.

- [ ] **Step 3: Implement reminders**

Create `backend/api/services/reminders.py`:

```python
"""Selecting + formatting the evening-before reminder digest. Pure DB reads +
string formatting — no push/network here (see push_sender)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.device import Device
from api.models.item import Item
from api.models.user import User

_MAX_LISTED = 5


async def users_with_devices(db: AsyncSession) -> list[User]:
    rows = await db.execute(
        select(User)
        .join(Device, Device.user_id == User.id)
        .where(User.deleted_at.is_(None), Device.deleted_at.is_(None))
        .distinct()
    )
    return list(rows.scalars().all())


async def device_tokens(db: AsyncSession, user: User) -> list[str]:
    rows = await db.execute(
        select(Device.fcm_token).where(
            Device.user_id == user.id, Device.deleted_at.is_(None)
        )
    )
    return list(rows.scalars().all())


async def tomorrow_events(db: AsyncSession, user: User, target_date: str) -> list[Item]:
    rows = await db.execute(
        select(Item)
        .where(
            Item.user_id == user.id,
            Item.deleted_at.is_(None),
            Item.status == "open",
            Item.item_type == "event",
            Item.event_date == target_date,
        )
        .order_by(Item.event_time)
    )
    return list(rows.scalars().all())


def format_digest(items) -> tuple[str, str]:
    parts: list[str] = []
    for item in items[:_MAX_LISTED]:
        title = item.event_title or "Event"
        parts.append(f"{title} {item.event_time}" if item.event_time else title)
    body = " · ".join(parts)
    extra = len(items) - _MAX_LISTED
    if extra > 0:
        body += f" · and {extra} more"
    return "Tomorrow's schedule", body
```

- [ ] **Step 4: Run tests + full suite**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_reminders.py -q && ./.venv/bin/python -m pytest -q`
Expected: PASS; full suite green.

- [ ] **Step 5: Commit**

```bash
git add backend/api/services/reminders.py backend/tests/test_reminders.py
git commit -m "feat(backend): reminder selection + digest formatting

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: `reminder_tick` (core scheduler logic)

**Files:**
- Create: `backend/api/services/reminder_scheduler.py` (the `reminder_tick` + prune; scheduler start/stop lands in Task 5)
- Test: `backend/tests/test_reminder_tick.py`

**Interfaces:**
- Consumes: `push_sender.send_digest` (Task 2), `reminders.*` (Task 3), `settings.reminder_tz`/`reminder_hour`, `Device` model.
- Produces: `async reminder_tick(session_factory, *, now: datetime.datetime | None = None) -> None` — opens its own session via `session_factory`; off-hour → no-op; else per eligible user sends the digest, prunes dead tokens, sets `last_reminder_date`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_reminder_tick.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_reminder_tick.py -q`
Expected: FAIL — `api.services.reminder_scheduler` doesn't exist.

- [ ] **Step 3: Implement `reminder_tick`**

Create `backend/api/services/reminder_scheduler.py`:

```python
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
```

- [ ] **Step 4: Run tests + full suite**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_reminder_tick.py -q && ./.venv/bin/python -m pytest -q`
Expected: PASS; full suite green.

- [ ] **Step 5: Commit**

```bash
git add backend/api/services/reminder_scheduler.py backend/tests/test_reminder_tick.py
git commit -m "feat(backend): reminder_tick (evening digest, per-user dedup + token prune)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Scheduler wiring (APScheduler + lifespan + deps)

**Files:**
- Modify: `backend/api/services/reminder_scheduler.py` (add `start_scheduler`/`stop_scheduler`)
- Modify: `backend/api/main.py` (lifespan)
- Modify: `backend/requirements.txt` (add `apscheduler`, `firebase-admin`)
- Test: `backend/tests/test_reminder_scheduler.py`

**Interfaces:**
- Consumes: `reminder_tick` (Task 4), `push_sender.is_configured`, `get_session_factory`.
- Produces: `start_scheduler() -> None` (starts an hourly `AsyncIOScheduler` job **only if configured**; sets module `_scheduler`), `stop_scheduler() -> None`.

- [ ] **Step 1: Add the dependencies**

In `backend/requirements.txt`, add:

```
apscheduler
firebase-admin
```

Run: `cd backend && ./.venv/bin/pip install apscheduler firebase-admin`
Expected: both install.

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_reminder_scheduler.py`:

```python
from api.config.settings import settings
from api.services import reminder_scheduler


def test_start_scheduler_inert_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "firebase_credentials_json", "")
    reminder_scheduler._scheduler = None

    reminder_scheduler.start_scheduler()

    # No scheduler created when the sender isn't configured.
    assert reminder_scheduler._scheduler is None
    reminder_scheduler.stop_scheduler()  # safe no-op


def test_start_scheduler_starts_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "firebase_credentials_json", '{"x": 1}')
    reminder_scheduler._scheduler = None
    started = {}

    class FakeScheduler:
        def add_job(self, *a, **k):
            started["job"] = True
        def start(self):
            started["started"] = True
        def shutdown(self, wait=False):
            started["stopped"] = True

    monkeypatch.setattr(reminder_scheduler, "_make_scheduler", lambda: FakeScheduler())

    reminder_scheduler.start_scheduler()
    assert started.get("job") and started.get("started")
    assert reminder_scheduler._scheduler is not None

    reminder_scheduler.stop_scheduler()
    assert started.get("stopped")
    assert reminder_scheduler._scheduler is None
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_reminder_scheduler.py -q`
Expected: FAIL — `start_scheduler`/`stop_scheduler`/`_make_scheduler` don't exist.

- [ ] **Step 4: Add the scheduler start/stop**

Append to `backend/api/services/reminder_scheduler.py`:

```python
def _make_scheduler():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    return AsyncIOScheduler()


def start_scheduler() -> None:
    """Start the hourly reminder job — only if push is configured (inert
    otherwise, so the app runs exactly as today when unset)."""
    global _scheduler
    if not push_sender.is_configured():
        _log.info("reminders: FIREBASE_CREDENTIALS_JSON unset — scheduler not started")
        return
    from apscheduler.triggers.cron import CronTrigger

    from api.db.session import get_session_factory

    session_factory = get_session_factory()
    _scheduler = _make_scheduler()
    _scheduler.add_job(
        reminder_tick,
        CronTrigger(minute=0),
        kwargs={"session_factory": session_factory},
        id="reminder_tick",
        replace_existing=True,
    )
    _scheduler.start()
    _log.info("reminders: hourly scheduler started")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
```

- [ ] **Step 5: Wire the lifespan**

In `backend/api/main.py`, add the import and update the lifespan:

```python
from api.services.reminder_scheduler import start_scheduler, stop_scheduler
```

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()
    await engine.dispose()
```

- [ ] **Step 6: Run tests + full suite**

Run: `cd backend && ./.venv/bin/python -m pytest tests/test_reminder_scheduler.py -q && ./.venv/bin/python -m pytest -q`
Expected: PASS; full suite green (unconfigured in tests → the real lifespan doesn't start a live scheduler).

- [ ] **Step 7: Commit**

```bash
git add backend/api/services/reminder_scheduler.py backend/api/main.py backend/requirements.txt backend/tests/test_reminder_scheduler.py
git commit -m "feat(backend): APScheduler hourly reminder job wired into the lifespan (inert until configured)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Security audit + activation checklist + HANDOFF

**Files:**
- Create: `docs/track-b-push-activation.md`
- Modify: `backend/.env.example`, `HANDOFF.md`

- [ ] **Step 1: Security audit**

Dispatch `@security-auditor` on the feature diff. Focus: the Firebase service-account JSON is env-only (never DB, never logged); the digest (event titles) reaches only the user's own device via FCM, never the ad layer (D19) and no raw body (D5); reminder queries are scoped by `user_id` + `deleted_at`; dead-token pruning soft-deletes only the failed tokens; the engine is provably inert when unconfigured. Address any BLOCK.

- [ ] **Step 2: Document the env vars**

Add to `backend/.env.example` (with empty/default values):

```
# Push reminders (Track B) — inert unless FIREBASE_CREDENTIALS_JSON is set.
FIREBASE_CREDENTIALS_JSON=
REMINDER_TZ=America/Toronto
REMINDER_HOUR=18
```

- [ ] **Step 3: Write the activation checklist**

Create `docs/track-b-push-activation.md` documenting the user-gated steps to turn the engine on: (1) create a Firebase project; (2) register the iOS app (bundle id) + Android app (package `com.bettersaas.mamaflow.mamaflow` + SHA-1 `8B:E8:14:1C:8C:E8:73:1F:EB:2D:52:1A:8B:EF:4A:67:7C:D1:B8:B9`) → download `GoogleService-Info.plist` / `google-services.json`; (3) upload an APNs auth key (iOS push); (4) create a service account → JSON → set `FIREBASE_CREDENTIALS_JSON` on Railway; (5) the **remaining code follow-up** (separate task): frontend Firebase init + notification permission + FCM token fetch/refresh + `DeviceRegistrar` call + message handlers, plus adding the `com.google.gms.google-services` Gradle plugin and the config files — built only after the config files exist (adding it before crashes the app like AdMob did).

- [ ] **Step 4: Update HANDOFF**

In `HANDOFF.md`, update the Track B row: the reminder **engine** (sender + scheduler + digest) is built + tested, inert until `FIREBASE_CREDENTIALS_JSON`; user runs the `d4e3f2a1b0c9` migration + follows `docs/track-b-push-activation.md`; the frontend Firebase wiring remains the gated follow-up.

- [ ] **Step 5: Commit + push**

```bash
git add docs/track-b-push-activation.md backend/.env.example HANDOFF.md
git commit -m "docs: Track B push activation checklist + HANDOFF (reminder engine built, inert)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push
```

---

## Self-review notes

- **Spec coverage:** push sender (Task 2), reminder selection/format (Task 3), scheduler tick + dedup + prune (Task 4), APScheduler lifespan wiring + deps (Task 5), config + migration (Task 1), inert-until-configured (Tasks 2/5), audit + activation checklist + HANDOFF (Task 6). Gated frontend/console work documented, not built.
- **Type consistency:** `is_configured`, `dead_tokens_from_responses`, `send_digest`, `users_with_devices`, `device_tokens`, `tomorrow_events`, `format_digest`, `reminder_tick(session_factory, *, now)`, `start_scheduler`/`stop_scheduler`/`_make_scheduler`, `settings.firebase_credentials_json`/`reminder_tz`/`reminder_hour`, `User.last_reminder_date` are used with identical signatures across tasks.
- **Migration revision** `d4e3f2a1b0c9` chains from the current head `c3d2e1f0a9b8` (devices).
