"""Tests for the get_current_user JWT dependency (Phase A)."""

import uuid

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from api.auth.dependencies import get_current_user
from api.auth.jwt import create_access_token
from api.services.users import get_or_create_user


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def test_returns_user_for_valid_token(db, session_factory):
    user = await get_or_create_user(db, "parent@example.com")
    token = create_access_token(subject=str(user.id), email=user.email)

    resolved = await get_current_user(_creds(token), db, session_factory)

    assert resolved.id == user.id


async def test_rejects_missing_credentials(db, session_factory):
    with pytest.raises(HTTPException) as exc:
        await get_current_user(None, db, session_factory)
    assert exc.value.status_code == 401


async def test_rejects_invalid_token(db, session_factory):
    with pytest.raises(HTTPException) as exc:
        await get_current_user(_creds("garbage"), db, session_factory)
    assert exc.value.status_code == 401


async def test_rejects_token_for_unknown_user(db, session_factory):
    token = create_access_token(subject=str(uuid.uuid4()), email="ghost@example.com")
    with pytest.raises(HTTPException) as exc:
        await get_current_user(_creds(token), db, session_factory)
    assert exc.value.status_code == 401


async def test_rejects_soft_deleted_user(db, session_factory):
    from datetime import datetime, timezone

    user = await get_or_create_user(db, "parent@example.com")
    user.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    token = create_access_token(subject=str(user.id), email=user.email)

    with pytest.raises(HTTPException) as exc:
        await get_current_user(_creds(token), db, session_factory)
    assert exc.value.status_code == 401


# --- Liveness write (2026-07-28 audit BLOCK) ---
#
# The first cut did this write on the REQUEST's session and, on failure,
# rolled back. rollback() expires every loaded object, including the `user`
# being returned — so the endpoint's next plain `user.id` raised
# MissingGreenlet and 500'd. A transient DB blip became a guaranteed failure
# of all authenticated traffic: the exact opposite of the intent.


async def test_authenticated_request_records_liveness(db, session_factory):
    """The dependency must actually drive last_seen_at — auto-sync's dormancy
    skip is only as good as this write."""
    import datetime

    from api.models.user import User

    user = await get_or_create_user(db, "parent@example.com")
    user.last_seen_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=30)
    await db.commit()
    token = create_access_token(subject=str(user.id), email=user.email)

    await get_current_user(_creds(token), db, session_factory)

    async with session_factory() as check:
        fresh = await check.get(User, user.id)
        age = datetime.datetime.now(datetime.UTC) - fresh.last_seen_at.replace(
            tzinfo=datetime.UTC
        )
    assert age.total_seconds() < 60


async def test_liveness_write_is_throttled(db, session_factory):
    """It runs on EVERY authenticated request; an unthrottled write would add a
    row update to every API call for a value needing day-level accuracy."""
    import datetime

    from api.models.user import User

    user = await get_or_create_user(db, "parent@example.com")
    recent = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=5)
    user.last_seen_at = recent
    await db.commit()
    token = create_access_token(subject=str(user.id), email=user.email)

    await get_current_user(_creds(token), db, session_factory)

    async with session_factory() as check:
        fresh = await check.get(User, user.id)
    assert fresh.last_seen_at.replace(tzinfo=datetime.UTC) == recent.replace(
        tzinfo=datetime.UTC
    )


async def test_a_failing_liveness_write_still_authenticates(db, session_factory):
    """The regression that mattered: a DB fault in the liveness write must not
    fail the request NOR expire the returned user (MissingGreenlet)."""
    user = await get_or_create_user(db, "parent@example.com")
    await db.commit()
    token = create_access_token(subject=str(user.id), email=user.email)

    def exploding_factory():
        raise RuntimeError("database is on fire")

    resolved = await get_current_user(_creds(token), db, exploding_factory)

    # Authenticated as normal...
    assert resolved.id == user.id
    # ...and still usable: these plain attribute reads are what every endpoint
    # does, and what raised MissingGreenlet under the old rollback().
    assert resolved.email == "parent@example.com"
    assert resolved.provider == "google"
