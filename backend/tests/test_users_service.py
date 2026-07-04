import datetime

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
