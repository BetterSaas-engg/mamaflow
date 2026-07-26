"""Provider-neutral reader errors (moved from google_token for multi-provider).

google_token re-exports ReauthRequired so existing imports keep the SAME class
identity — `except ReauthRequired` works regardless of import path.
"""


class ReauthRequired(Exception):
    """The stored credential is unusable (missing, unrefreshable, revoked app
    password, AUTHENTICATIONFAILED at the provider). The user must sign in
    again. Carries NO detail (no email, no credential material) — the caller
    already knows the user_id and logs types-only, so this exception must
    never smuggle PII into a traceback."""
