"""POST /api/v1/auth/google/web (spec 2026-07-18): browser PKCE exchange against
the WEB OAuth client -> same app JWT, shorter TTL. Google is never hit live."""

import datetime

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


async def test_exchange_code_web_internals(monkeypatch):
    """Exercises exchange_code_web's real body (no wholesale monkeypatch):
    the POST payload carries the web client id+secret and the derived
    redirect_uri, the id_token audience is the web client id, and the
    returned creds carry an absolute future expiry."""
    monkeypatch.setattr(settings, "web_app_origins", "https://app.mamaflow.example")
    monkeypatch.setattr(settings, "google_client_id", "web-client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "google_client_secret", "web-client-secret")

    recorded_post = {}
    recorded_audience = {}

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "access_token": "at",
                "refresh_token": "rt",
                "id_token": "idt",
                "expires_in": 3600,
                "scope": "s1 s2",
            }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def post(self, url, data=None):
            recorded_post["url"] = url
            recorded_post["data"] = data
            return _FakeResponse()

    import httpx
    from google.oauth2 import id_token as google_id_token

    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    def _fake_verify(token, request, audience):
        recorded_audience["audience"] = audience
        return {"email": "web@example.com"}

    monkeypatch.setattr(google_id_token, "verify_oauth2_token", _fake_verify)

    creds, email = await oauth.exchange_code_web("c", "v")

    assert recorded_post["data"]["client_id"] == "web-client-id.apps.googleusercontent.com"
    assert recorded_post["data"]["client_secret"] == "web-client-secret"
    assert recorded_post["data"]["redirect_uri"] == "https://app.mamaflow.example/auth.html"
    assert recorded_post["data"]["grant_type"] == "authorization_code"

    assert recorded_audience["audience"] == "web-client-id.apps.googleusercontent.com"

    assert creds["client_secret"] == "web-client-secret"
    expiry = datetime.datetime.fromisoformat(creds["expiry"])
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=datetime.UTC)
    assert expiry > datetime.datetime.now(datetime.UTC)

    assert email == "web@example.com"


async def test_web_auth_unconfigured_origins_returns_400_before_network(client, monkeypatch):
    """Ops-misconfiguration path: WEB_APP_ORIGINS unset means web_redirect_uri()
    raises before any network call, so exchange_code_web is intentionally left
    unpatched here — if this hangs, that no-network assumption broke."""
    monkeypatch.setattr(settings, "web_app_origins", "")

    resp = await client.post("/api/v1/auth/google/web", json=BODY)

    assert resp.status_code == 400
    assert "WEB_APP_ORIGINS" not in resp.text
    assert "Traceback" not in resp.text
    assert resp.json()["detail"] == "Invalid authorization code"
