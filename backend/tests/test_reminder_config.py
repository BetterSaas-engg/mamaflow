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
