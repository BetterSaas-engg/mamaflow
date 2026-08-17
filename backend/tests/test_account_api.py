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
from api.services.mail_connections import ensure_connection
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


async def test_token_store_calls_run_off_the_event_loop(client, db, monkeypatch):
    """With TOKEN_STORE_BACKEND=secret-manager, get/delete are blocking gRPC
    round-trips — they must not run on the event loop (revoke_gmail_token in
    between them already doesn't)."""
    import threading

    user, token = await _user_with_token(db)
    monkeypatch.setattr(account_service, "revoke_gmail_token", lambda creds: None)

    call_threads = {}

    def rec_get(email):
        call_threads["get"] = threading.get_ident()
        return {"token": "at"}

    def rec_delete_all(email):
        call_threads["delete"] = threading.get_ident()

    monkeypatch.setattr(account_service.token_store, "get_token", rec_get)
    monkeypatch.setattr(account_service.token_store, "delete_all_tokens", rec_delete_all)

    resp = await client.delete("/api/v1/account", headers=_auth(token))

    assert resp.status_code == 204
    assert call_threads.get("get") not in (None, threading.get_ident())
    assert call_threads.get("delete") not in (None, threading.get_ident())


async def test_delete_account_requires_auth(client):
    resp = await client.delete("/api/v1/account")
    assert resp.status_code == 401


async def test_delete_account_purges_credentials_under_all_providers(client, db, monkeypatch):
    """Audit BLOCK 2: an account that passed through multiple providers must
    leave NO live credential behind on deletion — not just the current one."""
    monkeypatch.setattr(account_service, "revoke_gmail_token", lambda creds: None)
    user, token = await _user_with_token(db, email="switcher@icloud.com")
    # Simulate history: a leftover Yahoo app password + the current iCloud one.
    token_store.store_token(user.email, {"kind": "imap_app_password"}, provider="yahoo")
    token_store.store_token(user.email, {"kind": "imap_app_password"}, provider="icloud")
    user.provider = "icloud"
    await db.commit()

    resp = await client.delete("/api/v1/account", headers=_auth(token))

    assert resp.status_code == 204
    assert token_store.get_token(user.email, "yahoo") is None
    assert token_store.get_token(user.email, "icloud") is None
    assert token_store.get_token(user.email) is None  # google key too


# --- Plan / mailbox usage (D44) ---


async def test_me_reports_free_tier_limits_by_default(client, db, monkeypatch):
    """Everyone starts free: 1 mailbox, 1 member, ads on."""
    user, token = await _user_with_token(db)

    body = (await client.get("/api/v1/account/me", headers=_auth(token))).json()

    assert body["tier"] == "free"
    assert body["ads_enabled"] is True
    assert body["member_limit"] == 1
    assert body["mailboxes"] == {
        "connected": 0,
        "limit": 1,
        "can_add_another": True,
    }


async def test_me_shows_the_free_cap_reached_once_a_mailbox_is_connected(
    client, db, monkeypatch
):
    user, token = await _user_with_token(db)
    await ensure_connection(db, user, 'google', user.email)

    body = (await client.get("/api/v1/account/me", headers=_auth(token))).json()

    assert body["mailboxes"]["connected"] == 1
    assert body["mailboxes"]["can_add_another"] is False


async def test_me_reflects_a_paid_tier(client, db, monkeypatch):
    user, token = await _user_with_token(db)
    user.tier = "family"
    await db.commit()
    await ensure_connection(db, user, 'google', user.email)

    body = (await client.get("/api/v1/account/me", headers=_auth(token))).json()

    assert body["tier"] == "family"
    assert body["ads_enabled"] is False
    assert body["member_limit"] == 2
    assert body["mailboxes"]["limit"] == 3  # shared across the household (D47)
    assert body["mailboxes"]["can_add_another"] is True  # 1 of 3 used


async def test_me_degrades_an_unknown_tier_to_free(client, db, monkeypatch):
    """A stale row or billing bug must not hand out a paid allowance, and must
    report what the user ACTUALLY got rather than echoing the bad value."""
    user, token = await _user_with_token(db)
    user.tier = "enterprise-lol"
    await db.commit()

    body = (await client.get("/api/v1/account/me", headers=_auth(token))).json()

    assert body["tier"] == "free"
    assert body["mailboxes"]["limit"] == 1
    assert body["ads_enabled"] is True


async def test_disconnecting_a_mailbox_frees_the_slot(client, db, monkeypatch):
    """Since mail_connections the slot is released by an explicit disconnect,
    not by a credential silently going bad — the user can see and undo it."""
    user, token = await _user_with_token(db)
    conn = await ensure_connection(db, user, "google", user.email)
    monkeypatch.setattr(
        "api.services.mail_connections.delete_token", lambda email, provider: None
    )

    before = (await client.get("/api/v1/account/me", headers=_auth(token))).json()
    assert before["mailboxes"]["can_add_another"] is False

    resp = await client.delete(
        f"/api/v1/account/mailboxes/{conn.id}", headers=_auth(token)
    )
    assert resp.status_code == 204

    after = (await client.get("/api/v1/account/me", headers=_auth(token))).json()
    assert after["mailboxes"]["connected"] == 0
    assert after["mailboxes"]["can_add_another"] is True


async def test_me_requires_authentication(client):
    assert (await client.get("/api/v1/account/me")).status_code == 401
