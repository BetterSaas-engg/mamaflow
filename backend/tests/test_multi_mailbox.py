"""Multi-mailbox (D44): several mailboxes per user, capped by tier.

Before `mail_connections`, connecting a mailbox PURGED the previous one, so a
second mailbox was impossible and the paid tiers had nothing to sell. These
tests pin the properties that make the feature safe rather than merely working:
cost stays bounded across mailboxes, a dead mailbox doesn't take the others
down, and no credential outlives its connection.

Mail/Claude are mocked — never live (testing skill).
"""

import pytest

from api.auth import token_store
from api.auth.jwt import create_access_token
from api.config.settings import settings as app_settings
from api.schemas.family_event import ExtractionResponse
from api.services import sync_runner
from api.services.ai_extractor import ExtractionUsage
from api.services.mail_connections import (
    MailboxLimitReached,
    ensure_connection,
    list_connections,
    remove_connection,
)
from api.services.reader_errors import ReauthRequired
from api.services.users import get_or_create_user


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _user(db, email="parent@example.com", tier="free"):
    user = await get_or_create_user(db, email)
    user.tier = tier
    await db.commit()
    return user, create_access_token(subject=str(user.id), email=user.email)


def _wire(monkeypatch, per_mailbox: dict[str, list[str]], seen: list):
    """Each mailbox serves its own message ids, so we can tell which mailbox a
    message came from."""

    def list_ids(email, provider="google"):
        return list(per_mailbox.get(email, []))

    def fetch_metadata(email, ids, provider="google"):
        return [
            {"message_id": i, "sender": "school@x.org", "subject": "S", "date": "Mon"}
            for i in ids
        ]

    monkeypatch.setattr(sync_runner, "list_recent_ids", list_ids)
    monkeypatch.setattr(sync_runner, "fetch_metadata", fetch_metadata)
    monkeypatch.setattr(
        sync_runner,
        "fetch_message_bodies",
        lambda email, ids, provider="google": {i: "practice on Thursday" for i in ids},
    )

    def fake_extract(body, subject, sender, message_id="", email_date="", provider="google"):
        seen.append(message_id)
        return ExtractionResponse(events=[]), ExtractionUsage(input_tokens=1, output_tokens=1)

    monkeypatch.setattr(sync_runner, "extract_events", fake_extract)


# --- sync across mailboxes ---


async def test_sync_reads_every_connected_mailbox(client, db, monkeypatch):
    monkeypatch.setattr(app_settings, "sync_cooldown_seconds", 0)
    monkeypatch.setattr(app_settings, "extraction_daily_call_budget", 10_000)
    user, token = await _user(db, tier="pro")
    await ensure_connection(db, user, "google", "parent@example.com")
    await ensure_connection(db, user, "yahoo", "parent@yahoo.com")

    seen: list[str] = []
    _wire(
        monkeypatch,
        {"parent@example.com": ["g1", "g2"], "parent@yahoo.com": ["y1"]},
        seen,
    )

    await client.post("/api/v1/sync", headers=_auth(token))

    assert set(seen) == {"g1", "g2", "y1"}


async def test_the_per_run_cap_is_shared_across_mailboxes(client, db, monkeypatch):
    """The cost property. Applied PER MAILBOX, a family with several mailboxes
    would multiply the per-tick Claude spend — the same runaway shape as D39."""
    monkeypatch.setattr(app_settings, "sync_cooldown_seconds", 0)
    monkeypatch.setattr(app_settings, "sync_max_messages_per_run", 5)
    monkeypatch.setattr(app_settings, "extraction_daily_call_budget", 10_000)
    user, token = await _user(db, tier="pro")
    await ensure_connection(db, user, "google", "parent@example.com")
    await ensure_connection(db, user, "yahoo", "parent@yahoo.com")

    seen: list[str] = []
    _wire(
        monkeypatch,
        {
            "parent@example.com": [f"g{i}" for i in range(10)],
            "parent@yahoo.com": [f"y{i}" for i in range(10)],
        },
        seen,
    )

    await client.post("/api/v1/sync", headers=_auth(token))

    assert len(seen) == 5, f"cap applied per mailbox, not per run: {len(seen)}"


async def test_one_dead_mailbox_does_not_stop_the_others(client, db, monkeypatch):
    """A revoked app password on one mailbox must not silently stop the mail
    flowing from the rest — the whole reason to support more than one."""
    monkeypatch.setattr(app_settings, "sync_cooldown_seconds", 0)
    monkeypatch.setattr(app_settings, "extraction_daily_call_budget", 10_000)
    user, token = await _user(db, tier="pro")
    await ensure_connection(db, user, "google", "parent@example.com")
    await ensure_connection(db, user, "yahoo", "dead@yahoo.com")

    seen: list[str] = []
    _wire(monkeypatch, {"parent@example.com": ["g1"]}, seen)
    healthy = sync_runner.list_recent_ids

    def list_ids(email, provider="google"):
        if email == "dead@yahoo.com":
            raise ReauthRequired
        return healthy(email, provider)

    monkeypatch.setattr(sync_runner, "list_recent_ids", list_ids)

    await client.post("/api/v1/sync", headers=_auth(token))
    status = (await client.get("/api/v1/sync/status", headers=_auth(token))).json()

    assert seen == ["g1"]
    assert status["status"] == "done"


async def test_all_mailboxes_dead_is_reported_as_needing_sign_in(
    client, db, monkeypatch
):
    monkeypatch.setattr(app_settings, "sync_cooldown_seconds", 0)
    user, token = await _user(db)
    await ensure_connection(db, user, "yahoo", "dead@yahoo.com")

    def list_ids(email, provider="google"):
        raise ReauthRequired

    monkeypatch.setattr(sync_runner, "list_recent_ids", list_ids)

    await client.post("/api/v1/sync", headers=_auth(token))
    status = (await client.get("/api/v1/sync/status", headers=_auth(token))).json()

    assert status["status"] == "failed"
    assert "sign in" in status["error"].lower()


async def test_a_user_with_no_mailboxes_syncs_nothing(client, db, monkeypatch):
    """Disconnecting every mailbox means there is nothing to read — it must not
    fall back to the identity email and keep syncing anyway."""
    monkeypatch.setattr(app_settings, "sync_cooldown_seconds", 0)
    user, token = await _user(db)
    seen: list[str] = []
    _wire(monkeypatch, {"parent@example.com": ["g1"]}, seen)

    await client.post("/api/v1/sync", headers=_auth(token))

    assert seen == []


# --- caps ---


async def test_free_tier_cannot_add_a_second_mailbox(db):
    user, _ = await _user(db, tier="free")
    await ensure_connection(db, user, "google", "parent@example.com")

    with pytest.raises(MailboxLimitReached):
        await ensure_connection(db, user, "yahoo", "second@yahoo.com")


async def test_pro_can_add_a_second_but_not_a_third(db):
    user, _ = await _user(db, tier="pro")
    await ensure_connection(db, user, "google", "parent@example.com")
    await ensure_connection(db, user, "yahoo", "second@yahoo.com")

    with pytest.raises(MailboxLimitReached):
        await ensure_connection(db, user, "icloud", "third@icloud.com")


async def test_reauthenticating_an_existing_mailbox_is_never_capped(db):
    """A rotated app password on a mailbox you already have is not an addition,
    and must not be refused just because you're at your limit."""
    user, _ = await _user(db, tier="free")
    first = await ensure_connection(db, user, "google", "parent@example.com")

    again = await ensure_connection(db, user, "google", "parent@example.com")

    assert again.id == first.id


async def test_disconnecting_frees_a_slot_and_reconnecting_revives_the_row(
    db, monkeypatch
):
    deleted: list[tuple] = []
    monkeypatch.setattr(
        "api.services.mail_connections.delete_token",
        lambda email, provider: deleted.append((email, provider)),
    )
    user, _ = await _user(db, tier="free")
    conn = await ensure_connection(db, user, "google", "parent@example.com")

    await remove_connection(db, user, conn)
    assert deleted == [("parent@example.com", "google")]  # credential destroyed
    assert await list_connections(db, user.id) == []

    # Reconnecting the same address must revive the tombstone, not collide with
    # it on the partial unique index.
    again = await ensure_connection(db, user, "google", "parent@example.com")
    assert again.id == conn.id


async def test_email_is_normalized_so_case_cannot_smuggle_an_extra_mailbox(db):
    """Casing/whitespace must resolve to the SAME mailbox — otherwise a free
    user could hold two connections by varying the case, and the cap would be
    trivially bypassable."""
    user, _ = await _user(db, tier="free")
    first = await ensure_connection(db, user, "google", "Parent@Example.com")

    again = await ensure_connection(db, user, "google", "  parent@EXAMPLE.com  ")

    assert again.id == first.id
    assert len(await list_connections(db, user.id)) == 1


# --- API ---


async def test_disconnect_endpoint_will_not_touch_another_users_mailbox(
    client, db, monkeypatch
):
    """A connection id must never be enough on its own."""
    monkeypatch.setattr(
        "api.services.mail_connections.delete_token", lambda email, provider: None
    )
    victim, _ = await _user(db, email="victim@example.com")
    theirs = await ensure_connection(db, victim, "google", "victim@example.com")
    _, attacker_token = await _user(db, email="attacker@example.com")

    resp = await client.delete(
        f"/api/v1/account/mailboxes/{theirs.id}", headers=_auth(attacker_token)
    )

    assert resp.status_code == 404
    assert len(await list_connections(db, victim.id)) == 1


async def test_mailboxes_endpoint_lists_only_your_own(client, db):
    user, token = await _user(db, tier="pro")
    await ensure_connection(db, user, "google", "parent@example.com")
    await ensure_connection(db, user, "yahoo", "parent@yahoo.com")
    other, _ = await _user(db, email="other@example.com")
    await ensure_connection(db, other, "google", "other@example.com")

    body = (await client.get("/api/v1/account/mailboxes", headers=_auth(token))).json()

    assert {m["email"] for m in body} == {"parent@example.com", "parent@yahoo.com"}


async def test_adding_a_mailbox_over_the_cap_is_refused_before_any_imap_call(
    client, db, monkeypatch
):
    """Don't make the user wait on a network round trip — or hold a credential
    — for a request we already know we're rejecting."""
    verified = []
    monkeypatch.setattr(
        "api.routers.account.verify_and_store_imap_mailbox",
        lambda payload, request: verified.append(payload),
    )
    user, token = await _user(db, tier="free")
    await ensure_connection(db, user, "google", "parent@example.com")

    resp = await client.post(
        "/api/v1/account/mailboxes",
        headers=_auth(token),
        json={
            "provider": "yahoo",
            "email": "second@yahoo.com",
            "app_password": "abcd efgh ijkl mnop",
        },
    )

    assert resp.status_code == 402
    assert verified == [], "verified a credential for a request we were rejecting"


async def test_add_mailbox_requires_authentication(client):
    resp = await client.post(
        "/api/v1/account/mailboxes",
        json={
            "provider": "yahoo",
            "email": "x@yahoo.com",
            "app_password": "abcd efgh ijkl mnop",
        },
    )
    assert resp.status_code == 401


async def test_connecting_an_address_under_a_new_provider_destroys_the_old_credential(
    db,
):
    """D38's guarantee, re-scoped to the mailbox: no address may keep a live
    credential under a provider it is no longer connected through."""
    user, _ = await _user(db)
    token_store.store_token("parent@example.com", {"token": "ya29-stale"}, "google")

    await ensure_connection(db, user, "yahoo", "parent@example.com")

    assert token_store.get_token("parent@example.com", "google") is None
