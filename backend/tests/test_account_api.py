"""Delete-account endpoint (Track D slice 2). Google revocation is mocked."""

import datetime

from sqlalchemy import select

from api.auth import token_store
from api.auth.jwt import create_access_token
from api.models.device import Device
from api.models.item import Item
from api.schemas.family_event import FamilyItem
from api.services import account as account_service
from api.services.items import persist_items
from api.services.users import get_or_create_user


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _user_with_token(db, email="parent@example.com"):
    user = await get_or_create_user(db, email)
    return user, create_access_token(subject=str(user.id), email=user.email)


async def test_delete_account_soft_deletes_and_revokes(client, db, monkeypatch):
    user, token = await _user_with_token(db)
    await persist_items(
        db, user, "m1",
        [FamilyItem(item_type="event", event_title="Soccer", date="2026-06-20")],
    )
    db.add(Device(user_id=user.id, fcm_token="fcm-1", platform="ios"))
    await db.commit()
    token_store.store_token(user.email, {"refresh_token": "rt", "token": "at"})

    revoked = {}
    monkeypatch.setattr(account_service, "revoke_gmail_token",
                        lambda creds: revoked.update(creds))

    resp = await client.delete("/api/v1/account", headers=_auth(token))

    assert resp.status_code == 204
    # user soft-deleted — the endpoint committed via the `client` fixture's own
    # session, so this session's identity-mapped `user` (loaded earlier by
    # _user_with_token) is stale; db.get() alone short-circuits on the
    # identity map without re-querying. Use the async-aware refresh to pick up
    # the other session's committed change.
    await db.refresh(user)
    refreshed = user
    assert refreshed.deleted_at is not None
    # items soft-deleted
    items = (await db.execute(select(Item).where(Item.user_id == user.id))).scalars().all()
    assert all(i.deleted_at is not None for i in items)
    # devices soft-deleted
    devs = (await db.execute(select(Device).where(Device.user_id == user.id))).scalars().all()
    assert all(d.deleted_at is not None for d in devs)
    # token revoked (with the stored creds) AND dropped
    assert revoked == {"refresh_token": "rt", "token": "at"}
    assert token_store.get_token(user.email) is None


async def test_deleted_account_jwt_is_rejected(client, db, monkeypatch):
    user, token = await _user_with_token(db)
    monkeypatch.setattr(account_service, "revoke_gmail_token", lambda creds: None)

    await client.delete("/api/v1/account", headers=_auth(token))
    # The same JWT now names a soft-deleted user -> 401 (get_current_user guard).
    after = await client.get("/api/v1/items", headers=_auth(token))
    assert after.status_code == 401


async def test_delete_account_survives_revocation_failure(client, db, monkeypatch):
    user, token = await _user_with_token(db)
    token_store.store_token(user.email, {"token": "at"})

    def boom(creds):
        raise RuntimeError("google down")
    # delete_account must swallow revocation errors (revoke_gmail_token is
    # best-effort); the account is still deleted and the token still dropped.
    monkeypatch.setattr(account_service, "revoke_gmail_token", boom)

    resp = await client.delete("/api/v1/account", headers=_auth(token))

    assert resp.status_code == 204
    assert token_store.get_token(user.email) is None


async def test_delete_account_requires_auth(client):
    resp = await client.delete("/api/v1/account")
    assert resp.status_code == 401
