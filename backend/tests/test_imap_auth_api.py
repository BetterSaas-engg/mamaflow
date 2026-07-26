"""POST /api/v1/auth/imap — app-password sign-in (the connection IS the
sign-in). FakeIMAP only; asserts the full error taxonomy, throttle behavior,
and that the app password never leaks into logs or validation bodies."""

import imaplib

import pytest
from sqlalchemy import select

from api.auth.jwt import decode_access_token
from api.auth.token_store import get_token
from api.models.user import User
from api.services import auth_throttle
from api.auth import imap_auth

PASSWORD = "abcd efgh ijkl mnop"


class FakeIMAP:
    fail_login = False
    fail_select = False
    raise_network: Exception | None = None

    def __init__(self, host, port, timeout=None):
        if FakeIMAP.raise_network is not None:
            raise FakeIMAP.raise_network

    def login(self, user, password):
        if FakeIMAP.fail_login:
            raise imaplib.IMAP4.error(b"[AUTHENTICATIONFAILED] LOGIN failed")
        return "OK", [b""]

    def select(self, mailbox, readonly=False):
        return ("NO", [b""]) if FakeIMAP.fail_select else ("OK", [b"1"])

    def logout(self):
        return "BYE", [b""]


@pytest.fixture(autouse=True)
def fake_imap(monkeypatch):
    FakeIMAP.fail_login = False
    FakeIMAP.fail_select = False
    FakeIMAP.raise_network = None
    monkeypatch.setattr(imap_auth.imaplib, "IMAP4_SSL", FakeIMAP)
    auth_throttle._reset()
    yield
    auth_throttle._reset()


def _payload(email="parent@rogers.com", provider="yahoo", password=PASSWORD):
    return {"provider": provider, "email": email, "app_password": password}


async def test_success_creates_user_stores_credential_returns_jwt(client, db):
    resp = await client.post("/api/v1/auth/imap", json=_payload())

    assert resp.status_code == 200
    body = resp.json()
    claims = decode_access_token(body["access_token"])
    assert claims["email"] == "parent@rogers.com"

    row = (await db.execute(select(User).where(User.email == "parent@rogers.com"))).scalar_one()
    assert row.provider == "yahoo"

    cred = get_token("parent@rogers.com", "yahoo")
    assert cred["kind"] == "imap_app_password"
    assert cred["app_password"] == PASSWORD.replace(" ", "")  # spaces normalized


async def test_wrong_password_401_with_app_password_hint(client, caplog):
    FakeIMAP.fail_login = True

    resp = await client.post("/api/v1/auth/imap", json=_payload())

    assert resp.status_code == 401
    assert "app password" in resp.json()["detail"]
    # Types-only logging: the password must never appear anywhere in logs.
    assert PASSWORD.replace(" ", "") not in caplog.text
    assert PASSWORD not in caplog.text


async def test_mailbox_unavailable_401_message(client):
    FakeIMAP.fail_select = True

    resp = await client.post("/api/v1/auth/imap", json=_payload(provider="icloud",
                                                               email="p@icloud.com"))

    assert resp.status_code == 401
    assert "mailbox isn't accessible" in resp.json()["detail"]


async def test_provider_unreachable_503_and_not_throttled(client):
    FakeIMAP.raise_network = TimeoutError("connect timeout")

    for _ in range(6):  # more than the per-email failure cap
        resp = await client.post("/api/v1/auth/imap", json=_payload())
        assert resp.status_code == 503  # never flips to 429 — outages don't count


async def test_unknown_provider_400(client):
    resp = await client.post("/api/v1/auth/imap", json=_payload(provider="aol"))
    assert resp.status_code == 400
    # google is a known provider but not an IMAP one — same rejection
    resp = await client.post("/api/v1/auth/imap", json=_payload(provider="google"))
    assert resp.status_code == 400


async def test_sixth_failure_for_same_email_throttles(client):
    FakeIMAP.fail_login = True

    for _ in range(5):
        assert (await client.post("/api/v1/auth/imap", json=_payload())).status_code == 401

    resp = await client.post("/api/v1/auth/imap", json=_payload())
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


async def test_provider_switch_updates_user_and_drops_google_credential(client, db):
    from api.auth.token_store import store_token
    from api.services.users import get_or_create_user

    user = await get_or_create_user(db, "parent@rogers.com")  # google identity
    store_token(user.email, {"token": "ya29-something"})  # google credential

    resp = await client.post("/api/v1/auth/imap", json=_payload())

    assert resp.status_code == 200
    await db.refresh(user)
    assert user.provider == "yahoo"
    assert get_token(user.email) is None  # google credential cleaned up
    assert get_token(user.email, "yahoo") is not None


async def test_validation_error_never_echoes_password(client):
    resp = await client.post(
        "/api/v1/auth/imap",
        json={"provider": "yahoo", "email": "x@y.com"},  # missing app_password
    )
    assert resp.status_code == 422
    assert PASSWORD not in resp.text

    resp = await client.post(
        "/api/v1/auth/imap",
        json={"provider": "yahoo", "email": 123, "app_password": PASSWORD},
    )
    assert resp.status_code == 422
    assert PASSWORD.replace(" ", "") not in resp.text
    assert PASSWORD not in resp.text  # SecretStr masks even invalid-payload echoes


async def test_empty_password_is_401_not_500(client):
    resp = await client.post("/api/v1/auth/imap", json=_payload(password="   "))
    assert resp.status_code == 401


# --- Audit BLOCK 1: IMAP command-injection guard ---


async def test_crlf_in_email_is_rejected_before_imap(client):
    FakeIMAP.fail_login = False
    resp = await client.post(
        "/api/v1/auth/imap",
        json=_payload(email="victim@yahoo.com\r\nA002 LOGIN attacker pw"),
    )
    assert resp.status_code == 422  # never reaches imaplib


async def test_crlf_in_app_password_is_rejected(client):
    resp = await client.post(
        "/api/v1/auth/imap",
        json=_payload(password="good\r\nA002 CAPABILITY"),
    )
    assert resp.status_code == 422


async def test_email_without_at_is_rejected(client):
    resp = await client.post("/api/v1/auth/imap", json=_payload(email="notanemail"))
    assert resp.status_code == 422


# --- Audit BLOCK 2: no stale credential survives a provider switch ---


async def test_switching_between_imap_providers_purges_the_old_one(client, db):
    from api.auth.token_store import get_token

    await client.post("/api/v1/auth/imap", json=_payload(email="p@icloud.com", provider="icloud",
                                                         password="aaaa bbbb cccc dddd"))
    assert get_token("p@icloud.com", "icloud") is not None

    # Same address now connects via Yahoo — the iCloud credential must be gone.
    await client.post("/api/v1/auth/imap", json=_payload(email="p@icloud.com", provider="yahoo"))

    assert get_token("p@icloud.com", "yahoo") is not None
    assert get_token("p@icloud.com", "icloud") is None
