"""auth_throttle unit tests — windows, success reset, bounded maps."""

import pytest

from api.config.settings import settings
from api.services import auth_throttle


@pytest.fixture(autouse=True)
def clean():
    auth_throttle._reset()
    yield
    auth_throttle._reset()


def test_per_ip_cap_counts_all_attempts():
    for _ in range(settings.imap_auth_max_attempts_per_ip):
        allowed, _ = auth_throttle.check("1.2.3.4", f"u{_}@x.com")
        assert allowed
    allowed, retry = auth_throttle.check("1.2.3.4", "another@x.com")
    assert not allowed
    assert retry >= 1
    # A different IP is unaffected.
    assert auth_throttle.check("5.6.7.8", "u@x.com")[0]


def test_per_email_cap_counts_failures_only():
    for _ in range(settings.imap_auth_max_failures_per_email):
        ip = f"9.9.9.{_}"  # spread across IPs so only the email cap applies
        assert auth_throttle.check(ip, "victim@x.com")[0]
        auth_throttle.record_failure(ip, "victim@x.com")

    allowed, retry = auth_throttle.check("9.9.9.100", "victim@x.com")
    assert not allowed and retry >= 1


def test_success_clears_email_failures():
    for i in range(settings.imap_auth_max_failures_per_email - 1):
        auth_throttle.record_failure(f"8.8.8.{i}", "flaky@x.com")
    auth_throttle.record_success("flaky@x.com")
    for i in range(settings.imap_auth_max_failures_per_email - 1):
        auth_throttle.record_failure(f"7.7.7.{i}", "flaky@x.com")
    assert auth_throttle.check("6.6.6.6", "flaky@x.com")[0]  # still under cap


def test_window_expiry_frees_the_email(monkeypatch):
    base = 1000.0
    monkeypatch.setattr(auth_throttle.time, "monotonic", lambda: base)
    for i in range(settings.imap_auth_max_failures_per_email):
        auth_throttle.record_failure(f"2.2.2.{i}", "late@x.com")
    assert not auth_throttle.check("3.3.3.3", "late@x.com")[0]

    monkeypatch.setattr(
        auth_throttle.time, "monotonic",
        lambda: base + settings.imap_auth_window_seconds + 1,
    )
    assert auth_throttle.check("3.3.3.3", "late@x.com")[0]


def test_raw_email_never_stored_in_maps():
    auth_throttle.record_failure("1.1.1.1", "Secret.Person@example.com")
    for key in auth_throttle._email_failures:
        assert "secret.person" not in key.lower()
