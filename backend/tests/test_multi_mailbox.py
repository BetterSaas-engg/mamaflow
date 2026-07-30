"""Multi-mailbox (D44): several mailboxes per user, capped by tier.

Before `mail_connections`, connecting a mailbox PURGED the previous one, so a
second mailbox was impossible and the paid tiers had nothing to sell. These
tests pin the properties that make the feature safe rather than merely working:
cost stays bounded across mailboxes, a dead mailbox doesn't take the others
down, and no credential outlives its connection.

Mail/Claude are mocked — never live (testing skill).
"""

import imaplib

import pytest

from api.auth import token_store
from api.auth.jwt import create_access_token
from api.config.settings import settings as app_settings
from api.schemas.family_event import ExtractionResponse
from api.services import sync_runner
from api.services.ai_extractor import ExtractionUsage
from api.services.mail_connections import (
    MailboxAlreadyConnected,
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


# --- The real add-mailbox endpoint (audit: no test ever called it) ---
#
# Every previous test mocked `verify_and_store_imap_mailbox` — the very
# function that was broken — so the suite stayed green while the endpoint
# 500'd on every real call. These drive the actual router with only the IMAP
# socket faked.


class _FakeIMAP:
    fail_login = False

    def __init__(self, host, port, timeout=None):
        pass

    def login(self, user, password):
        if _FakeIMAP.fail_login:
            raise imaplib.IMAP4.error(b"[AUTHENTICATIONFAILED]")
        return "OK", [b""]

    def select(self, mailbox, readonly=False):
        return "OK", [b"1"]

    def logout(self):
        return "BYE", [b""]


@pytest.fixture
def fake_imap(monkeypatch):
    from api.auth import imap_auth
    from api.services import auth_throttle

    _FakeIMAP.fail_login = False
    monkeypatch.setattr(imap_auth.imaplib, "IMAP4_SSL", _FakeIMAP)
    auth_throttle._reset()
    yield
    auth_throttle._reset()


async def test_pro_user_can_actually_add_a_second_mailbox(client, db, fake_imap):
    """The happy path, end to end through the real endpoint. Its absence is
    what let an infinite self-recursion ship green."""
    user, token = await _user(db, tier="pro")
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

    assert resp.status_code == 201, resp.text
    assert resp.json()["email"] == "second@yahoo.com"
    assert {c.email for c in await list_connections(db, user.id)} == {
        "parent@example.com",
        "second@yahoo.com",
    }
    # And the credential really was stored for the new mailbox.
    assert token_store.get_token("second@yahoo.com", "yahoo") is not None


async def test_add_mailbox_rejects_a_bad_app_password(client, db, fake_imap):
    _FakeIMAP.fail_login = True
    user, token = await _user(db, tier="pro")

    resp = await client.post(
        "/api/v1/account/mailboxes",
        headers=_auth(token),
        json={
            "provider": "yahoo",
            "email": "second@yahoo.com",
            "app_password": "wrong wrong wrong",
        },
    )

    assert resp.status_code == 401
    assert await list_connections(db, user.id) == []


async def test_sign_in_still_works_through_the_shared_helper(client, db, fake_imap):
    """The helper is shared with sign-in; refactoring it must not break that."""
    resp = await client.post(
        "/api/v1/auth/imap",
        json={
            "provider": "yahoo",
            "email": "new@yahoo.com",
            "app_password": "abcd efgh ijkl mnop",
        },
    )

    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "new@yahoo.com"


# --- Audit follow-ups (2026-07-30 security review) ---


async def test_a_rejected_over_cap_attempt_destroys_no_credential(db):
    """The purge used to run BEFORE the cap check, so an attempt that ended in
    402 had already wiped a live credential for that address — including one
    belonging to a different account."""
    owner, _ = await _user(db, email="owner@example.com", tier="free")
    await ensure_connection(db, owner, "yahoo", "shared@family.com")
    token_store.store_token(
        "shared@family.com", {"kind": "imap_app_password"}, "yahoo"
    )

    other, _ = await _user(db, email="other@example.com", tier="free")
    await ensure_connection(db, other, "google", "other@example.com")

    with pytest.raises(Exception):
        await ensure_connection(db, other, "icloud", "shared@family.com")

    assert token_store.get_token("shared@family.com", "yahoo") is not None


async def test_a_mailbox_cannot_be_connected_by_two_accounts(db):
    """Credentials are keyed globally by (email, provider) with no user in the
    key, so a second connection would clobber the first's secret and either
    party disconnecting would break the other."""
    first, _ = await _user(db, email="mum@example.com", tier="free")
    await ensure_connection(db, first, "yahoo", "shared@family.com")

    second, _ = await _user(db, email="dad@example.com", tier="free")

    with pytest.raises(MailboxAlreadyConnected):
        await ensure_connection(db, second, "yahoo", "shared@family.com")


async def test_add_mailbox_endpoint_reports_a_taken_mailbox_as_conflict(
    client, db, fake_imap
):
    owner, _ = await _user(db, email="owner@example.com", tier="pro")
    await ensure_connection(db, owner, "yahoo", "shared@family.com")
    user, token = await _user(db, email="other@example.com", tier="pro")

    resp = await client.post(
        "/api/v1/account/mailboxes",
        headers=_auth(token),
        json={
            "provider": "yahoo",
            "email": "shared@family.com",
            "app_password": "abcd efgh ijkl mnop",
        },
    )

    assert resp.status_code == 409


async def test_account_deletion_purges_every_mailbox_not_just_the_identity(
    db, monkeypatch
):
    user, _ = await _user(db, tier="pro")
    await ensure_connection(db, user, "google", "parent@example.com")
    await ensure_connection(db, user, "yahoo", "second@yahoo.com")
    token_store.store_token("parent@example.com", {"token": "t"}, "google")
    token_store.store_token("second@yahoo.com", {"kind": "imap"}, "yahoo")
    monkeypatch.setattr(
        "api.services.account.revoke_gmail_token", lambda creds: None
    )

    from api.services.account import delete_account

    await delete_account(db, user)

    assert token_store.get_token("parent@example.com", "google") is None
    assert token_store.get_token("second@yahoo.com", "yahoo") is None


async def test_a_credential_store_failure_does_not_abandon_the_other_mailboxes(
    db, monkeypatch
):
    """One transient Secret Manager fault used to abort the loop, leaving the
    remaining secrets alive while their rows were already soft-deleted — i.e.
    invisible forever."""
    user, _ = await _user(db, tier="pro")
    await ensure_connection(db, user, "yahoo", "broken@yahoo.com")
    await ensure_connection(db, user, "icloud", "fine@icloud.com")
    token_store.store_token("fine@icloud.com", {"kind": "imap"}, "icloud")

    real_delete = token_store.delete_all_tokens

    def flaky(email):
        if email == "broken@yahoo.com":
            raise RuntimeError("secret manager unavailable")
        return real_delete(email)

    monkeypatch.setattr("api.services.account.token_store.delete_all_tokens", flaky)
    from api.services.account import delete_account

    await delete_account(db, user)

    # The healthy mailbox was still purged...
    assert token_store.get_token("fine@icloud.com", "icloud") is None
    # ...and the failed one stays live so it remains discoverable for cleanup,
    # rather than being soft-deleted with its credential still out there.
    from sqlalchemy import select as _select

    from api.models.mail_connection import MailConnection

    rows = await db.execute(
        _select(MailConnection.email).where(MailConnection.deleted_at.is_(None))
    )
    assert [r[0] for r in rows] == ["broken@yahoo.com"]
