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
