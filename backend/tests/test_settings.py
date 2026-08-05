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


def test_a_short_secret_warns_in_production_but_still_boots(monkeypatch, caplog):
    """Refusing to boot would take production down for a key that is merely
    shorter than ideal rather than guessable — and rotating it signs every user
    out (no refresh flow, D31), so it must be a scheduled act."""
    import logging

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "short-but-not-a-placeholder")
    with caplog.at_level(logging.WARNING):
        s = Settings(_env_file=None)

    assert s.secret_key == "short-but-not-a-placeholder"
    assert "RFC 7518" in caplog.text


def test_a_long_secret_is_silent(monkeypatch, caplog):
    import logging

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "x" * 48)
    with caplog.at_level(logging.WARNING):
        Settings(_env_file=None)

    assert "RFC 7518" not in caplog.text


def test_a_placeholder_secret_still_refuses_to_boot(monkeypatch):
    """Unchanged: a known placeholder IS trivially forgeable."""
    import pytest

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "dev-secret-key")
    with pytest.raises(ValueError):
        Settings(_env_file=None)
