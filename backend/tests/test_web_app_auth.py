"""POST /api/v1/auth/google/web (spec 2026-07-18): browser PKCE exchange against
the WEB OAuth client -> same app JWT, shorter TTL. Google is never hit live."""

import pytest

from api.auth import oauth
from api.auth.jwt import decode_access_token
from api.auth.token_store import get_token
from api.config.settings import settings

FAKE_CREDS = {
    "token": "ya29.web-access",
    "refresh_token": "1//web-refresh",
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": "web-client-id",
    "client_secret": "web-secret",
    "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
}
BODY = {"code": "web-code-123", "code_verifier": "web-verifier-xyz"}


def test_web_redirect_uri_derived_from_first_origin(monkeypatch):
    monkeypatch.setattr(settings, "web_app_origins", "https://app.mamaflow.example, https://x.vercel.app")
    assert oauth.web_redirect_uri() == "https://app.mamaflow.example/auth.html"


def test_web_redirect_uri_unconfigured_raises(monkeypatch):
    monkeypatch.setattr(settings, "web_app_origins", "")
    with pytest.raises(ValueError):
        oauth.web_redirect_uri()


async def test_valid_code_returns_jwt_with_web_ttl(client, db, monkeypatch):
    async def _fake_exchange(code, code_verifier):
        assert code == "web-code-123" and code_verifier == "web-verifier-xyz"
        return FAKE_CREDS, "Parent@Example.com"

    monkeypatch.setattr(oauth, "exchange_code_web", _fake_exchange)

    resp = await client.post("/api/v1/auth/google/web", json=BODY)

    assert resp.status_code == 200
    body = resp.json()
    assert body["expires_in"] == settings.web_token_expire_minutes * 60
    assert body["user"]["email"] == "parent@example.com"
    claims = decode_access_token(body["access_token"])
    assert claims["sub"] == body["user"]["id"]


async def test_gmail_tokens_stored_server_side(client, monkeypatch):
    async def _fake_exchange(code, code_verifier):
        return FAKE_CREDS, "parent@example.com"

    monkeypatch.setattr(oauth, "exchange_code_web", _fake_exchange)
    await client.post("/api/v1/auth/google/web", json=BODY)
    stored = get_token("parent@example.com")
    assert stored is not None and stored["refresh_token"] == "1//web-refresh"


async def test_web_auth_stores_token_off_the_event_loop(client, monkeypatch):
    import threading

    async def _fake_exchange(code, code_verifier):
        return FAKE_CREDS, "parent@example.com"

    monkeypatch.setattr(oauth, "exchange_code_web", _fake_exchange)
    store_threads = []
    monkeypatch.setattr(
        oauth, "store_token",
        lambda email, data: store_threads.append(threading.get_ident()),
    )

    resp = await client.post("/api/v1/auth/google/web", json=BODY)

    assert resp.status_code == 200
    assert store_threads and store_threads[0] != threading.get_ident()


async def test_invalid_code_returns_400_sanitized(client, monkeypatch):
    async def _boom(code, code_verifier):
        raise ValueError("google exploded")

    monkeypatch.setattr(oauth, "exchange_code_web", _boom)
    resp = await client.post("/api/v1/auth/google/web", json=BODY)
    assert resp.status_code == 400
    assert "exploded" not in resp.text
