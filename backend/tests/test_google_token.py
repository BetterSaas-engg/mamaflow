"""Manual refresh for the mobile PKCE Gmail credential.

iOS OAuth clients are public (no client_secret), but google-auth's
Credentials.refresh() refuses to refresh a credential whose client_secret is
None. Public clients refresh via the token endpoint with client_id +
refresh_token and NO secret (RFC 6749 §6). google_token.ensure_fresh does that.

Google's token endpoint is mocked here — tests never hit live OAuth.
"""

import datetime

import httpx
import pytest

from api.services import google_token
from api.services.google_token import ReauthRequired, ensure_fresh


def _iso(delta_seconds: int) -> str:
    return (
        datetime.datetime.now(datetime.UTC)
        + datetime.timedelta(seconds=delta_seconds)
    ).isoformat()


def _mobile_token(expiry_delta: int | None, refresh_token="FAKE-REFRESH"):
    td = {
        "token": "FAKE-OLD-ACCESS",
        "refresh_token": refresh_token,
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "ios.apps.googleusercontent.com",
        "client_secret": None,
        "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
    }
    if expiry_delta is not None:
        td["expiry"] = _iso(expiry_delta)
    return td


def _mock_google(monkeypatch, *, status=200, body=None, capture=None):
    def fake_post(url, data=None, timeout=None):
        if capture is not None:
            capture["url"] = url
            capture["data"] = data
        return httpx.Response(
            status, json=body or {"access_token": "new-access", "expires_in": 3600}
        )

    monkeypatch.setattr(google_token.httpx, "post", fake_post)


def test_expired_mobile_token_is_refreshed_and_restored(monkeypatch):
    stored = {}
    monkeypatch.setattr(
        google_token, "store_token", lambda email, td: stored.update({email: td})
    )
    capture = {}
    _mock_google(monkeypatch, capture=capture)

    out = ensure_fresh("p@x.com", _mobile_token(expiry_delta=-10))

    # The refresh POST carries client_id + refresh_token and NO secret.
    assert capture["data"]["grant_type"] == "refresh_token"
    assert capture["data"]["client_id"] == "ios.apps.googleusercontent.com"
    assert capture["data"]["refresh_token"] == "FAKE-REFRESH"
    assert "client_secret" not in capture["data"]
    # Returns the fresh access token and persists it (with a future expiry).
    assert out["token"] == "new-access"
    assert stored["p@x.com"]["token"] == "new-access"
    assert out["refresh_token"] == "FAKE-REFRESH"  # preserved


def test_fresh_mobile_token_is_not_refreshed(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(
        google_token.httpx, "post",
        lambda *a, **k: called.__setitem__("n", called["n"] + 1),
    )
    monkeypatch.setattr(google_token, "store_token", lambda *a, **k: None)

    out = ensure_fresh("p@x.com", _mobile_token(expiry_delta=3600))

    assert called["n"] == 0
    assert out["token"] == "FAKE-OLD-ACCESS"


def test_missing_expiry_is_treated_as_expired(monkeypatch):
    # Tokens stored before this fix have no "expiry" field — refresh them.
    monkeypatch.setattr(google_token, "store_token", lambda *a, **k: None)
    _mock_google(monkeypatch)
    out = ensure_fresh("p@x.com", _mobile_token(expiry_delta=None))
    assert out["token"] == "new-access"


def test_web_credential_is_left_for_google_auth(monkeypatch):
    # Web creds have a real client_secret; google-auth refreshes them natively.
    monkeypatch.setattr(
        google_token.httpx, "post",
        lambda *a, **k: pytest.fail("web creds must not be manually refreshed"),
    )
    web = _mobile_token(expiry_delta=-10)
    web["client_secret"] = "web-secret"
    out = ensure_fresh("p@x.com", web)
    assert out is web


def test_no_refresh_token_raises_reauth(monkeypatch):
    monkeypatch.setattr(google_token, "store_token", lambda *a, **k: None)
    with pytest.raises(ReauthRequired):
        ensure_fresh("p@x.com", _mobile_token(expiry_delta=-10, refresh_token=None))


def test_revoked_refresh_token_raises_reauth(monkeypatch):
    # Google returns 400 invalid_grant when the refresh token is revoked/expired.
    monkeypatch.setattr(google_token, "store_token", lambda *a, **k: None)
    _mock_google(monkeypatch, status=400, body={"error": "invalid_grant"})
    with pytest.raises(ReauthRequired):
        ensure_fresh("p@x.com", _mobile_token(expiry_delta=-10))


def test_reauth_carries_no_pii(monkeypatch):
    # The exception must not embed the email (it lands in tracebacks/logs).
    monkeypatch.setattr(google_token, "store_token", lambda *a, **k: None)
    _mock_google(monkeypatch, status=400, body={"error": "invalid_grant"})
    try:
        ensure_fresh("secret-user@x.com", _mobile_token(expiry_delta=-10))
        raise AssertionError("expected ReauthRequired")
    except ReauthRequired as exc:
        assert "secret-user@x.com" not in str(exc)


def test_transient_5xx_is_retryable_not_reauth(monkeypatch):
    # A Google-side 5xx must NOT force re-auth — it's transient (retry next tick).
    monkeypatch.setattr(google_token, "store_token", lambda *a, **k: None)
    _mock_google(monkeypatch, status=503, body={"error": "backend_error"})
    with pytest.raises(httpx.HTTPError):
        ensure_fresh("p@x.com", _mobile_token(expiry_delta=-10))
