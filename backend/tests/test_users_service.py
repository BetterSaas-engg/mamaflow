import datetime

from api.services import users as users_svc
from api.services.users import get_or_create_user


async def test_get_or_create_reactivates_soft_deleted_user(db):
    user = await get_or_create_user(db, "Parent@Example.com")
    original_id = user.id
    user.deleted_at = datetime.datetime.now(datetime.UTC)
    await db.commit()

    # Signing in again must reactivate the SAME row (email is unique) — not
    # crash on the unique constraint, not create a duplicate.
    again = await get_or_create_user(db, "parent@example.com")

    assert again.id == original_id
    assert again.deleted_at is None


async def test_get_or_create_returns_active_user(db):
    a = await get_or_create_user(db, "x@y.com")
    b = await get_or_create_user(db, "x@y.com")
    assert a.id == b.id


async def test_get_or_create_survives_concurrent_insert_race(db, monkeypatch):
    """Two simultaneous first sign-ins for the same new email: the loser of the
    check-then-insert race hits the unique constraint and must recover with the
    winner's row, not 500. Simulated by making the initial lookup miss once."""
    existing = await get_or_create_user(db, "race@x.com")

    real_find = users_svc._find_by_email
    calls = {"n": 0}

    async def flaky_find(db_, normalized):
        calls["n"] += 1
        if calls["n"] == 1:
            return None  # the "not found" read both racers saw
        return await real_find(db_, normalized)

    monkeypatch.setattr(users_svc, "_find_by_email", flaky_find)

    user = await get_or_create_user(db, "race@x.com")

    assert user.id == existing.id
