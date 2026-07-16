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
