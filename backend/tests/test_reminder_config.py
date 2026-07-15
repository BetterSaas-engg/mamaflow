import datetime

from api.config.settings import Settings, settings
from api.models.user import User
from api.services.users import get_or_create_user


def test_reminder_settings_defaults():
    assert settings.reminder_tz == "America/Toronto"
    assert settings.reminder_hour == 18
    assert settings.firebase_credentials_json == ""


def test_bad_reminder_hour_falls_back_instead_of_crashing(monkeypatch):
    # A cosmetic reminder knob must never take the whole API down (2026-07-15
    # prod outage: REMINDER_HOUR="10:30" -> ValidationError at import -> 502).
    monkeypatch.setenv("REMINDER_HOUR", "10:30")
    s = Settings(_env_file=None)
    assert s.reminder_hour == 18


def test_out_of_range_reminder_hour_falls_back(monkeypatch):
    monkeypatch.setenv("REMINDER_HOUR", "25")
    assert Settings(_env_file=None).reminder_hour == 18
    monkeypatch.setenv("REMINDER_HOUR", "-3")
    assert Settings(_env_file=None).reminder_hour == 18


def test_valid_reminder_hour_string_still_parses(monkeypatch):
    monkeypatch.setenv("REMINDER_HOUR", "20")
    assert Settings(_env_file=None).reminder_hour == 20


def test_bad_reminder_tz_falls_back(monkeypatch):
    monkeypatch.setenv("REMINDER_TZ", "Mars/Olympus_Mons")
    assert Settings(_env_file=None).reminder_tz == "America/Toronto"


async def test_user_last_reminder_date_roundtrips(db):
    user = await get_or_create_user(db, "p@x.com")
    user.last_reminder_date = datetime.date(2026, 7, 6)
    await db.commit()
    await db.refresh(user)
    assert user.last_reminder_date == datetime.date(2026, 7, 6)
    # default is None for a fresh user
    other = await get_or_create_user(db, "q@x.com")
    assert other.last_reminder_date is None
