"""Tests for Settings validation (Phase A audit hardening)."""

import pytest
from pydantic import ValidationError

from api.config.settings import Settings


def test_weak_secret_rejected_outside_development():
    with pytest.raises(ValidationError):
        Settings(environment="production", secret_key="dev-secret-key", _env_file=None)


def test_development_allows_weak_secret():
    s = Settings(environment="development", secret_key="dev-secret-key", _env_file=None)
    assert s.secret_key == "dev-secret-key"


def test_strong_secret_accepted_in_production():
    s = Settings(environment="production", secret_key="x" * 48, _env_file=None)
    assert s.environment == "production"


def test_default_session_ttl_is_30_days():
    """D31: mobile session JWTs last 30 days — the app has no refresh flow, and
    a 15-minute TTL forced a re-sign-in mid-use every quarter hour."""
    s = Settings(_env_file=None)
    assert s.access_token_expire_minutes == 30 * 24 * 60
