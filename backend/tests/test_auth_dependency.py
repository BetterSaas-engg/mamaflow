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


async def test_returns_user_for_valid_token(db):
    user = await get_or_create_user(db, "parent@example.com")
    token = create_access_token(subject=str(user.id), email=user.email)

    resolved = await get_current_user(_creds(token), db)

    assert resolved.id == user.id


async def test_rejects_missing_credentials(db):
    with pytest.raises(HTTPException) as exc:
        await get_current_user(None, db)
    assert exc.value.status_code == 401


async def test_rejects_invalid_token(db):
    with pytest.raises(HTTPException) as exc:
        await get_current_user(_creds("garbage"), db)
    assert exc.value.status_code == 401


async def test_rejects_token_for_unknown_user(db):
    token = create_access_token(subject=str(uuid.uuid4()), email="ghost@example.com")
    with pytest.raises(HTTPException) as exc:
        await get_current_user(_creds(token), db)
    assert exc.value.status_code == 401


async def test_rejects_soft_deleted_user(db):
    from datetime import datetime, timezone

    user = await get_or_create_user(db, "parent@example.com")
    user.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    token = create_access_token(subject=str(user.id), email=user.email)

    with pytest.raises(HTTPException) as exc:
        await get_current_user(_creds(token), db)
    assert exc.value.status_code == 401
