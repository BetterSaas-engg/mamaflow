"""Tests for POST /api/v1/auth/google/mobile (Phase A, requirement #1).

The Google code-exchange is mocked — tests never hit live Google.
"""

from api.auth import oauth
from api.auth.jwt import decode_access_token
from api.auth.token_store import get_token

FAKE_CREDS = {
    "token": "ya29.access",
    "refresh_token": "1//refresh",
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": "cid",
    "client_secret": "csecret",
    "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
}


async def test_valid_code_returns_jwt_and_creates_user(client, db, monkeypatch):
    monkeypatch.setattr(
        oauth, "exchange_server_auth_code",
        lambda code: (FAKE_CREDS, "Parent@Example.com"),
    )

    resp = await client.post(
        "/api/v1/auth/google/mobile", json={"server_auth_code": "serverauthcode123"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    assert body["user"]["email"] == "parent@example.com"

    # The returned JWT resolves to the created user.
    claims = decode_access_token(body["access_token"])
    assert claims["sub"] == body["user"]["id"]
    assert claims["email"] == "parent@example.com"


async def test_gmail_tokens_stored_server_side(client, monkeypatch):
    monkeypatch.setattr(
        oauth, "exchange_server_auth_code",
        lambda code: (FAKE_CREDS, "parent@example.com"),
    )

    await client.post(
        "/api/v1/auth/google/mobile", json={"server_auth_code": "code"}
    )

    # D4: refresh token kept server-side, keyed by the user's (normalized) email.
    stored = get_token("parent@example.com")
    assert stored is not None
    assert stored["refresh_token"] == "1//refresh"


async def test_invalid_code_returns_400(client, monkeypatch):
    def _boom(code):
        raise ValueError("bad code")

    monkeypatch.setattr(oauth, "exchange_server_auth_code", _boom)

    resp = await client.post(
        "/api/v1/auth/google/mobile", json={"server_auth_code": "nope"}
    )
    assert resp.status_code == 400
