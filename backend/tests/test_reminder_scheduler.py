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
