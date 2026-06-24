"""Tests for device registration (Phase D, requirement #4)."""

from sqlalchemy import func, select

from api.auth.jwt import create_access_token
from api.models.device import Device
from api.services.users import get_or_create_user


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _user_with_token(db, email="parent@example.com"):
    user = await get_or_create_user(db, email)
    return user, create_access_token(subject=str(user.id), email=user.email)


async def test_register_requires_auth(client):
    resp = await client.post(
        "/api/v1/devices/register", json={"fcm_token": "t", "platform": "ios"}
    )
    assert resp.status_code == 401


async def test_register_creates_device(client, db):
    _, token = await _user_with_token(db)

    resp = await client.post(
        "/api/v1/devices/register",
        json={"fcm_token": "tok1", "platform": "ios"},
        headers=_auth(token),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["platform"] == "ios"
    assert body["id"]


async def test_register_dedupes_by_token_and_updates(client, db):
    _, token = await _user_with_token(db)

    await client.post(
        "/api/v1/devices/register",
        json={"fcm_token": "tok1", "platform": "ios"},
        headers=_auth(token),
    )
    await client.post(
        "/api/v1/devices/register",
        json={"fcm_token": "tok1", "platform": "android"},
        headers=_auth(token),
    )

    count = await db.scalar(
        select(func.count()).select_from(Device).where(Device.fcm_token == "tok1")
    )
    assert count == 1
    dev = (await db.execute(select(Device).where(Device.fcm_token == "tok1"))).scalar_one()
    assert dev.platform == "android"


async def test_register_rejects_invalid_platform(client, db):
    _, token = await _user_with_token(db)

    resp = await client.post(
        "/api/v1/devices/register",
        json={"fcm_token": "t", "platform": "windows"},
        headers=_auth(token),
    )
    assert resp.status_code == 422
