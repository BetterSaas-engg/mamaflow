"""Auto-sync: settings knob, tick selection/isolation, scheduler wiring.
Gmail/Claude/GCP/scheduler are mocked — tests never hit live services."""

from api.config.settings import Settings


def test_auto_sync_enabled_defaults_true():
    assert Settings(_env_file=None).auto_sync_enabled is True


def test_auto_sync_enabled_parses_false(monkeypatch):
    monkeypatch.setenv("AUTO_SYNC_ENABLED", "false")
    assert Settings(_env_file=None).auto_sync_enabled is False


def test_bad_auto_sync_enabled_falls_back_true(monkeypatch):
    # Fail-soft (REMINDER_HOUR outage rule): garbage never crashes the API.
    monkeypatch.setenv("AUTO_SYNC_ENABLED", "banana")
    assert Settings(_env_file=None).auto_sync_enabled is True


import uuid

from api.config.settings import settings as app_settings
from api.services import auto_sync, sync_state
from api.services.users import get_or_create_user


class _JobRecorder:
    def __init__(self):
        self.calls: list[tuple[uuid.UUID, str]] = []

    async def __call__(self, user_id, user_email, session_factory):
        self.calls.append((user_id, user_email))


async def test_tick_syncs_token_holders_and_skips_tokenless(
    db, session_factory, monkeypatch
):
    a = await get_or_create_user(db, "a@x.com")
    b = await get_or_create_user(db, "b@x.com")
    await db.commit()
    sync_state._states.clear()
    monkeypatch.setattr(app_settings, "sync_cooldown_seconds", 0)

    # Only A has a stored Gmail token.
    monkeypatch.setattr(
        auto_sync, "get_token", lambda email: {"token": "t"} if email == "a@x.com" else None
    )
    recorder = _JobRecorder()
    monkeypatch.setattr(auto_sync, "run_sync_job", recorder)

    await auto_sync.auto_sync_tick(session_factory)

    assert recorder.calls == [(a.id, "a@x.com")]


async def test_tick_skips_soft_deleted_users(db, session_factory, monkeypatch):
    import datetime

    u = await get_or_create_user(db, "gone@x.com")
    u.deleted_at = datetime.datetime.now(datetime.UTC)
    await db.commit()
    sync_state._states.clear()

    monkeypatch.setattr(auto_sync, "get_token", lambda email: {"token": "t"})
    recorder = _JobRecorder()
    monkeypatch.setattr(auto_sync, "run_sync_job", recorder)

    await auto_sync.auto_sync_tick(session_factory)

    assert recorder.calls == []


async def test_tick_respects_running_and_cooldown(db, session_factory, monkeypatch):
    u = await get_or_create_user(db, "busy@x.com")
    await db.commit()
    sync_state._states.clear()
    monkeypatch.setattr(app_settings, "sync_cooldown_seconds", 3600)

    monkeypatch.setattr(auto_sync, "get_token", lambda email: {"token": "t"})
    recorder = _JobRecorder()
    monkeypatch.setattr(auto_sync, "run_sync_job", recorder)

    # Case 1: a sync is already running.
    assert sync_state.try_start(u.id)[0] == "started"
    await auto_sync.auto_sync_tick(session_factory)
    assert recorder.calls == []

    # Case 2: recently finished -> cooldown.
    sync_state.finish(
        u.id, messages_scanned=0, blocked=0, processed=0, items_created=0
    )
    await auto_sync.auto_sync_tick(session_factory)
    assert recorder.calls == []


async def test_one_user_failure_does_not_stop_the_pass(
    db, session_factory, monkeypatch
):
    await get_or_create_user(db, "boom@x.com")
    ok = await get_or_create_user(db, "ok@x.com")
    await db.commit()
    sync_state._states.clear()
    monkeypatch.setattr(app_settings, "sync_cooldown_seconds", 0)

    def token_or_boom(email):
        if email == "boom@x.com":
            raise RuntimeError("secret manager down")
        return {"token": "t"}

    monkeypatch.setattr(auto_sync, "get_token", token_or_boom)
    recorder = _JobRecorder()
    monkeypatch.setattr(auto_sync, "run_sync_job", recorder)

    await auto_sync.auto_sync_tick(session_factory)

    assert recorder.calls == [(ok.id, "ok@x.com")]


from api.services import reminder_scheduler


class _FakeScheduler:
    def __init__(self):
        self.jobs: dict[str, object] = {}
        self.started = False

    def add_job(self, func, trigger, kwargs=None, id=None, replace_existing=False):
        self.jobs[id] = trigger

    def start(self):
        self.started = True

    def shutdown(self, wait=False):
        pass


def _wire(monkeypatch, *, firebase: str, auto_sync: bool) -> _FakeScheduler:
    from api.config.settings import settings as app_settings

    fake = _FakeScheduler()
    monkeypatch.setattr(app_settings, "firebase_credentials_json", firebase)
    monkeypatch.setattr(app_settings, "auto_sync_enabled", auto_sync)
    monkeypatch.setattr(reminder_scheduler, "_make_scheduler", lambda: fake)
    reminder_scheduler._scheduler = None
    reminder_scheduler.start_scheduler()
    return fake


def test_scheduler_registers_both_jobs_when_both_wanted(monkeypatch):
    fake = _wire(monkeypatch, firebase='{"x": 1}', auto_sync=True)
    assert set(fake.jobs) == {"reminder_tick", "auto_sync_tick"}
    assert fake.started
    # Exact offsets: reminders :00, auto-sync :30 (spec).
    assert "minute='0'" in str(fake.jobs["reminder_tick"])
    assert "minute='30'" in str(fake.jobs["auto_sync_tick"])
    reminder_scheduler.stop_scheduler()


def test_scheduler_starts_with_only_auto_sync(monkeypatch):
    fake = _wire(monkeypatch, firebase="", auto_sync=True)
    assert set(fake.jobs) == {"auto_sync_tick"}
    assert fake.started
    reminder_scheduler.stop_scheduler()


def test_scheduler_starts_with_only_reminders(monkeypatch):
    fake = _wire(monkeypatch, firebase='{"x": 1}', auto_sync=False)
    assert set(fake.jobs) == {"reminder_tick"}
    assert fake.started
    reminder_scheduler.stop_scheduler()


def test_scheduler_inert_when_nothing_wanted(monkeypatch):
    _wire(monkeypatch, firebase="", auto_sync=False)
    assert reminder_scheduler._scheduler is None
    reminder_scheduler.stop_scheduler()  # safe no-op
