"""Provider dispatch for mail readers — the one place sync code asks
"which reader serves this user?".

Registry-keyed (auth_kind), so adding a provider (Phase 2: Microsoft Graph)
is a registry entry + a reader module — no changes here beyond one branch,
and none in sync_runner/auto_sync at all.
"""

from api.services import gmail_reader, imap_reader
from api.services.mail_providers import get_provider
from api.services.reader_errors import ReauthRequired


def fetch_recent_metadata(user_email: str, provider: str) -> list[dict]:
    if provider == "google":
        return gmail_reader.fetch_recent_metadata(user_email)
    spec = get_provider(provider)
    if spec is not None and spec.auth_kind == "imap-app-password":
        return imap_reader.fetch_recent_metadata(user_email, provider)
    # Unknown/unsupported provider on the user row — nothing to read until
    # they reconnect through a supported flow.
    raise ReauthRequired


def fetch_message_bodies(
    user_email: str, message_ids: list[str], provider: str
) -> dict[str, str]:
    if provider == "google":
        return gmail_reader.fetch_message_bodies(user_email, message_ids)
    spec = get_provider(provider)
    if spec is not None and spec.auth_kind == "imap-app-password":
        return imap_reader.fetch_message_bodies(user_email, message_ids, provider)
    raise ReauthRequired
