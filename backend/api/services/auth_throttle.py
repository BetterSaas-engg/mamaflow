"""Brute-force throttle for credential-based sign-in (POST /auth/imap).

That endpoint accepts arbitrary email+password pairs and relays them to
Yahoo/Apple — a credential-stuffing surface, and a way to get Mamaflow's
egress IP temporarily blocked by the provider. Two in-process fixed-window
limits (same Phase-0 pattern as sync_state / oauth's _pending_states;
resets on deploy, single-instance only — revisit with the D2 broker split):

  - per-IP: max N attempts (success or failure) per window
  - per-email: max M FAILED logins per window; a success clears the entry.
    Keyed by sha256(email) — raw emails never sit in this map.

503s (provider unreachable) are deliberately NOT counted as failures —
a provider outage must not lock users out.
"""

import hashlib
import time

from api.config.settings import settings

_MAX_ENTRIES = 5000  # bounded maps — evict oldest key when full

_ip_attempts: dict[str, list[float]] = {}
_email_failures: dict[str, list[float]] = {}


def _email_key(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()


def _pruned(stamps: list[float], now: float) -> list[float]:
    cutoff = now - settings.imap_auth_window_seconds
    return [s for s in stamps if s > cutoff]


def _evict_if_full(bucket: dict) -> None:
    while len(bucket) >= _MAX_ENTRIES:
        bucket.pop(next(iter(bucket)))


def _retry_after(stamps: list[float], now: float) -> int:
    oldest = min(stamps)
    return max(1, int(settings.imap_auth_window_seconds - (now - oldest)) + 1)


def check(ip: str, email: str) -> tuple[bool, int]:
    """(allowed, retry_after_seconds). Counts this call as one per-IP attempt
    when allowed."""
    now = time.monotonic()

    ip_stamps = _pruned(_ip_attempts.get(ip, []), now)
    if len(ip_stamps) >= settings.imap_auth_max_attempts_per_ip:
        _ip_attempts[ip] = ip_stamps
        return False, _retry_after(ip_stamps, now)

    email_stamps = _pruned(_email_failures.get(_email_key(email), []), now)
    if len(email_stamps) >= settings.imap_auth_max_failures_per_email:
        _email_failures[_email_key(email)] = email_stamps
        return False, _retry_after(email_stamps, now)

    _evict_if_full(_ip_attempts)
    ip_stamps.append(now)
    _ip_attempts[ip] = ip_stamps
    return True, 0


def record_failure(ip: str, email: str) -> None:
    now = time.monotonic()
    key = _email_key(email)
    _evict_if_full(_email_failures)
    stamps = _pruned(_email_failures.get(key, []), now)
    stamps.append(now)
    _email_failures[key] = stamps


def record_success(email: str) -> None:
    _email_failures.pop(_email_key(email), None)


def _reset() -> None:
    """Tests only."""
    _ip_attempts.clear()
    _email_failures.clear()
