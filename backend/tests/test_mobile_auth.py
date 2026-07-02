"""Tests for POST /api/v1/auth/google/mobile (PKCE code exchange, D23).

The Google token exchange is mocked — tests never hit live Google.
"""

from api.auth import oauth
from api.auth.jwt import decode_access_token
from api.auth.token_store import get_token

FAKE_CREDS = {
    "token": "ya29.access",
    "refresh_token": "1//refresh",
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": "ios-client-id",
    "client_secret": None,
    "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
}

BODY = {
    "code": "auth-code-123",
    "code_verifier": "pkce-verifier-xyz",
    "redirect_uri": "com.googleusercontent.apps.abc:/oauth2redirect",
}


async def test_valid_code_returns_jwt_and_creates_user(client, db, monkeypatch):
    async def _fake_exchange(code, code_verifier, redirect_uri):
        assert code == "auth-code-123"
        assert code_verifier == "pkce-verifier-xyz"
        return FAKE_CREDS, "Parent@Example.com"

    monkeypatch.setattr(oauth, "exchange_code_pkce", _fake_exchange)

    resp = await client.post("/api/v1/auth/google/mobile", json=BODY)

    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    assert body["user"]["email"] == "parent@example.com"

    claims = decode_access_token(body["access_token"])
    assert claims["sub"] == body["user"]["id"]
    assert claims["email"] == "parent@example.com"


async def test_gmail_tokens_stored_server_side(client, monkeypatch):
    async def _fake_exchange(code, code_verifier, redirect_uri):
        return FAKE_CREDS, "parent@example.com"

    monkeypatch.setattr(oauth, "exchange_code_pkce", _fake_exchange)

    await client.post("/api/v1/auth/google/mobile", json=BODY)

    stored = get_token("parent@example.com")
    assert stored is not None
    assert stored["refresh_token"] == "1//refresh"


async def test_invalid_code_returns_400(client, monkeypatch):
    async def _boom(code, code_verifier, redirect_uri):
        raise ValueError("bad code")

    monkeypatch.setattr(oauth, "exchange_code_pkce", _boom)

    resp = await client.post("/api/v1/auth/google/mobile", json=BODY)
    assert resp.status_code == 400
