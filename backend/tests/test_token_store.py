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
