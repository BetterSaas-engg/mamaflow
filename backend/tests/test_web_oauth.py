"""Tests for the legacy web OAuth flow (GET /google/callback) hardening.

Never hits live Google: the deny / missing-param / unknown-state paths fail
before any network call, and the happy path mocks the Flow and the id-token
verification at the module boundary.
"""

from types import SimpleNamespace

from api.auth import oauth
from api.auth.token_store import get_token


async def test_callback_denied_returns_400(client):
    """Clicking 'Deny' on Google's consent screen sends error=access_denied
    (and no code) — a friendly 400, not an unhandled KeyError."""
    resp = await client.get("/api/v1/auth/google/callback?error=access_denied")
    assert resp.status_code == 400


async def test_callback_missing_params_return_400(client):
    assert (await client.get("/api/v1/auth/google/callback")).status_code == 400
    assert (await client.get("/api/v1/auth/google/callback?state=s")).status_code == 400
    assert (await client.get("/api/v1/auth/google/callback?code=c")).status_code == 400


async def test_callback_unknown_state_returns_400(client):
    """Replay, or the in-memory state store was lost to a restart mid-login."""
    resp = await client.get("/api/v1/auth/google/callback?state=nope&code=c")
    assert resp.status_code == 400


async def test_callback_happy_path_stores_gmail_token(client, monkeypatch):
    creds = SimpleNamespace(
        token="t", refresh_token="r", token_uri="u", client_id="c",
        client_secret="s", scopes=["scope"], id_token="idtok",
    )
    flow = SimpleNamespace(
        credentials=creds, code_verifier=None, fetch_token=lambda code: None
    )
    monkeypatch.setattr(oauth, "_build_flow", lambda: flow)
    monkeypatch.setattr(
        "google.oauth2.id_token.verify_oauth2_token",
        lambda *a, **k: {"email": "web@example.com"},
    )
    oauth._pending_states["st1"] = "verifier"

    resp = await client.get("/api/v1/auth/google/callback?state=st1&code=abc")

    assert resp.status_code == 200
    assert flow.code_verifier == "verifier"
    stored = get_token("web@example.com")
    assert stored is not None
    assert stored["refresh_token"] == "r"


async def test_callback_stores_token_off_the_event_loop(client, monkeypatch):
    """With the secret-manager backend, store_token is a blocking gRPC call —
    it must not run on the event loop in the sign-in hot path."""
    import threading

    creds = SimpleNamespace(
        token="t", refresh_token="r", token_uri="u", client_id="c",
        client_secret="s", scopes=["scope"], id_token="idtok",
    )
    flow = SimpleNamespace(
        credentials=creds, code_verifier=None, fetch_token=lambda code: None
    )
    monkeypatch.setattr(oauth, "_build_flow", lambda: flow)
    monkeypatch.setattr(
        "google.oauth2.id_token.verify_oauth2_token",
        lambda *a, **k: {"email": "web-offloop@example.com"},
    )
    oauth._pending_states["st-offloop"] = "verifier"

    store_threads = []
    monkeypatch.setattr(
        oauth, "store_token",
        lambda email, data: store_threads.append(threading.get_ident()),
    )

    resp = await client.get("/api/v1/auth/google/callback?state=st-offloop&code=abc")

    assert resp.status_code == 200
    assert store_threads, "store_token was never called"
    assert store_threads[0] != threading.get_ident()


async def test_callback_google_failure_returns_400_not_500(client, monkeypatch):
    def _boom(code):
        raise ValueError("google exploded")

    flow = SimpleNamespace(credentials=None, code_verifier=None, fetch_token=_boom)
    monkeypatch.setattr(oauth, "_build_flow", lambda: flow)
    oauth._pending_states["st2"] = "verifier"

    resp = await client.get("/api/v1/auth/google/callback?state=st2&code=abc")

    assert resp.status_code == 400
    assert "exploded" not in resp.text  # sanitized


async def test_pending_states_are_capped(monkeypatch):
    """Abandoned logins must not grow the in-memory state dict forever."""
    monkeypatch.setattr(oauth, "_MAX_PENDING_STATES", 3)
    oauth._pending_states.clear()
    for i in range(5):
        oauth._remember_state(f"s{i}", f"v{i}")
    assert len(oauth._pending_states) == 3
    assert "s0" not in oauth._pending_states  # oldest evicted first
    assert "s4" in oauth._pending_states
