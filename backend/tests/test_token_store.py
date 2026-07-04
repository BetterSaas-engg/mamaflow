"""Tests for the pluggable Gmail token store (D4: tokens NEVER in the DB;
Secret Manager for persistence, in-memory for dev/tests).

The Secret Manager client is mocked — tests never hit live GCP.
"""

from unittest.mock import MagicMock

import pytest
from google.api_core import exceptions as gcp_exceptions

from api.auth.token_store import InMemoryTokenStore, SecretManagerTokenStore

CREDS = {"token": "ya29.x", "refresh_token": "1//r", "scopes": ["gmail.readonly"]}


# --- in-memory backend (dev/test default) ---


def test_memory_roundtrip():
    store = InMemoryTokenStore()
    store.store("parent@example.com", CREDS)
    assert store.get("parent@example.com") == CREDS
    assert store.get("nobody@example.com") is None


# --- Secret Manager backend ---


@pytest.fixture
def sm_client():
    return MagicMock()


def _store(sm_client):
    return SecretManagerTokenStore(project_id="proj-123", client=sm_client)


def test_secret_id_is_hashed_not_email(sm_client):
    store = _store(sm_client)
    secret_id = store.secret_id_for("Parent@Example.com")

    assert "parent" not in secret_id.lower().replace("gmail-token", "")
    assert "@" not in secret_id
    assert secret_id.startswith("gmail-token-")
    # Normalized casing yields the same id.
    assert secret_id == store.secret_id_for("parent@example.com")


def test_store_creates_secret_and_adds_version(sm_client):
    store = _store(sm_client)

    store.store("parent@example.com", CREDS)

    sm_client.create_secret.assert_called_once()
    sm_client.add_secret_version.assert_called_once()
    payload = sm_client.add_secret_version.call_args.kwargs["request"]["payload"]["data"]
    assert b"1//r" in payload


def test_store_on_existing_secret_just_adds_version(sm_client):
    sm_client.create_secret.side_effect = gcp_exceptions.AlreadyExists("exists")
    store = _store(sm_client)

    store.store("parent@example.com", CREDS)

    sm_client.add_secret_version.assert_called_once()


def test_get_reads_latest_version(sm_client):
    resp = MagicMock()
    resp.payload.data = b'{"token": "ya29.x", "refresh_token": "1//r"}'
    sm_client.access_secret_version.return_value = resp
    store = _store(sm_client)

    creds = store.get("parent@example.com")

    assert creds["refresh_token"] == "1//r"
    name = sm_client.access_secret_version.call_args.kwargs["request"]["name"]
    assert name.endswith("/versions/latest")


def test_get_missing_secret_returns_none(sm_client):
    sm_client.access_secret_version.side_effect = gcp_exceptions.NotFound("no")
    store = _store(sm_client)

    assert store.get("parent@example.com") is None


def test_get_uses_cache_after_store(sm_client):
    store = _store(sm_client)
    store.store("parent@example.com", CREDS)

    creds = store.get("parent@example.com")

    assert creds == CREDS
    sm_client.access_secret_version.assert_not_called()


def test_gcp_outage_raises_sanitized_error(sm_client):
    # PermissionDenied / ServiceUnavailable etc. must surface as a domain error
    # without GCP internals, not propagate raw (audit finding).
    from api.auth.token_store import TokenStoreError

    sm_client.access_secret_version.side_effect = gcp_exceptions.ServiceUnavailable("gcp guts")
    store = _store(sm_client)

    with pytest.raises(TokenStoreError) as exc:
        store.get("parent@example.com")
    assert "gcp guts" not in str(exc.value)


def test_store_is_built_lazily(monkeypatch):
    # A dev .env with TOKEN_STORE_BACKEND=secret-manager must not construct a
    # real GCP client at import/collection time — only on first use (audit
    # finding). Reset the lazy singleton and verify no client is built until
    # a token call happens.
    from api.auth import token_store
    from api.config.settings import settings as app_settings

    monkeypatch.setattr(token_store, "_store", None)
    monkeypatch.setattr(app_settings, "token_store_backend", "secret-manager")
    monkeypatch.setattr(app_settings, "gcp_project_id", "proj-123")

    built = []

    def _fake_init(self, project_id, client=None):
        built.append(project_id)
        self._cache = {}  # minimal state so list_users() works

    monkeypatch.setattr(token_store.SecretManagerTokenStore, "__init__", _fake_init)

    assert built == []  # nothing constructed yet
    token_store.get_token  # attribute access alone must not build either
    assert built == []

    token_store.list_users()  # first real use builds the backend
    assert built == ["proj-123"]


# --- delete tests ---


def test_in_memory_delete_removes_token():
    store = InMemoryTokenStore()
    store.store("a@b.com", {"token": "x"})
    assert store.get("a@b.com") == {"token": "x"}

    store.delete("a@b.com")

    assert store.get("a@b.com") is None


def test_in_memory_delete_absent_is_noop():
    store = InMemoryTokenStore()
    store.delete("nobody@b.com")  # must not raise
    assert store.get("nobody@b.com") is None


def test_in_memory_delete_normalizes_key():
    store = InMemoryTokenStore()
    store.store("A@B.com ", {"token": "x"})
    store.delete("A@B.com ")  # same form as stored (but not normalized by delete) must delete
    assert store.get("a@b.com") is None


def test_secret_manager_delete_swallows_not_found_and_evicts_cache(sm_client):
    store = _store(sm_client)
    sm_client.delete_secret.side_effect = gcp_exceptions.NotFound("absent")
    store._cache["a@b.com"] = {"token": "x"}
    store.delete("a@b.com")  # NotFound swallowed -> no raise
    assert "a@b.com" not in store._cache
    assert sm_client.delete_secret.called


def test_secret_manager_delete_sanitizes_api_error(sm_client, caplog):
    store = _store(sm_client)
    sm_client.delete_secret.side_effect = gcp_exceptions.GoogleAPIError("boom-SECRETVAL")
    with caplog.at_level("WARNING"):
        store.delete("a@b.com")  # must not raise
    assert "SECRETVAL" not in caplog.text  # exception detail not logged


def test_module_delete_token_uses_active_store(monkeypatch):
    from api.auth import token_store

    store = InMemoryTokenStore()
    monkeypatch.setattr(token_store, "_store", store)
    monkeypatch.setattr(token_store, "_get_store", lambda: store)
    store.store("c@d.com", {"token": "y"})

    token_store.delete_token("c@d.com")

    assert store.get("c@d.com") is None
