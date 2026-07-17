"""Refresh the mobile PKCE Gmail credential.

iOS OAuth clients are public (no client_secret, D23/D28), but google-auth's
Credentials.refresh() refuses to refresh a credential whose client_secret is
None. Public clients refresh via the token endpoint with client_id +
refresh_token and NO secret (RFC 6749 §6). This module does that manual refresh
and re-stores the fresh access token so it persists (Secret Manager, D4).

Web-flow credentials (a real client_secret) are left untouched — google-auth
refreshes those natively.
"""

import datetime
import logging

import httpx

from api.auth.token_store import store_token

_log = logging.getLogger(__name__)

# Refresh a little early so an about-to-expire token doesn't 401 mid-request.
_REFRESH_SKEW = datetime.timedelta(seconds=120)
_DEFAULT_LIFETIME = 3600


class ReauthRequired(Exception):
    """The stored credential cannot be refreshed (no refresh token, or the
    refresh token was revoked). The user must sign in again. Carries NO detail
    (no email, no token material) — the caller already knows the user_id and
    logs types-only, so this exception must never smuggle PII into a traceback."""


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _expiry_iso(lifetime_seconds: int) -> str:
    return (_now() + datetime.timedelta(seconds=lifetime_seconds)).isoformat()


def _is_expired(token_data: dict) -> bool:
    """A missing/invalid expiry counts as expired — tokens stored before this
    fix have no expiry, so refresh them once."""
    raw = token_data.get("expiry")
    if not raw:
        return True
    try:
        expiry = datetime.datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return True
    return _now() >= expiry - _REFRESH_SKEW


def ensure_fresh(user_email: str, token_data: dict) -> dict:
    """Return token_data with a non-expired access token.

    Mobile (client_secret is None) credentials past expiry are refreshed via
    Google's token endpoint and the fresh token is re-stored. Web credentials
    and not-yet-expired tokens are returned unchanged.
    """
    if token_data.get("client_secret") is not None:
        return token_data  # web credential — google-auth refreshes it natively
    if not _is_expired(token_data):
        return token_data

    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        raise ReauthRequired

    # Public-client refresh: client_id + refresh_token, NO secret.
    try:
        resp = httpx.post(
            token_data["token_uri"],
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": token_data["client_id"],
            },
            timeout=15,
        )
    except httpx.HTTPError as exc:
        # A transient network error is not a re-auth condition — surface it so
        # the sync retries next tick rather than pushing the user to sign in.
        _log.warning("token refresh transport error (%s)", type(exc).__name__)
        raise

    if resp.status_code >= 500:
        # Google-side hiccup — transient. Surface as an HTTP error so the sync
        # retries next tick instead of forcing a spurious "sign in again".
        _log.warning("token refresh got HTTP %s — transient", resp.status_code)
        raise httpx.HTTPError(f"token endpoint returned {resp.status_code}")
    if resp.status_code != 200:
        # 4xx (invalid_grant etc.) => the refresh token is dead => re-auth. Log
        # the error *code* only (a fixed enum), never the response body.
        try:
            code = resp.json().get("error", "")
        except ValueError:
            code = f"HTTP {resp.status_code}"
        _log.warning("token refresh rejected (%s) — re-auth required", code)
        raise ReauthRequired

    body = resp.json()
    lifetime = int(body.get("expires_in", _DEFAULT_LIFETIME))
    updated = {
        **token_data,
        "token": body["access_token"],
        "expiry": _expiry_iso(lifetime),
    }
    # Google usually omits refresh_token on refresh; keep the existing one.
    store_token(user_email, updated)
    return updated
