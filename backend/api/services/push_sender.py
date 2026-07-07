"""FCM push sender (firebase-admin, HTTP v1). Inert unless a Firebase
service-account JSON is configured (env only, never the DB, D4). Never logs a
token value or the digest text."""

import asyncio
import json
import logging

from api.config.settings import settings

_log = logging.getLogger(__name__)
_app = None  # firebase_admin app singleton (lazy)

# FCM errors that mean the token is permanently invalid -> prune the device.
_DEAD_ERROR_TYPES = {"UnregisteredError", "SenderIdMismatchError"}


def is_configured() -> bool:
    return bool(settings.firebase_credentials_json)


def dead_tokens_from_responses(tokens: list[str], responses) -> list[str]:
    """Tokens whose send failed with a permanent token error."""
    dead: list[str] = []
    for token, response in zip(tokens, responses):
        if not getattr(response, "success", False):
            if type(getattr(response, "exception", None)).__name__ in _DEAD_ERROR_TYPES:
                dead.append(token)
    return dead


def _send_sync(tokens: list[str], title: str, body: str) -> list[str]:
    global _app
    import firebase_admin
    from firebase_admin import credentials, messaging

    if _app is None:
        _app = firebase_admin.initialize_app(
            credentials.Certificate(json.loads(settings.firebase_credentials_json))
        )
    response = messaging.send_each_for_multicast(
        messaging.MulticastMessage(
            tokens=tokens,
            notification=messaging.Notification(title=title, body=body),
        )
    )
    return dead_tokens_from_responses(tokens, response.responses)


async def send_digest(tokens: list[str], title: str, body: str) -> list[str]:
    """Send a digest to the tokens; return the dead ones (to prune). No-op
    (returns []) when unconfigured or tokens is empty. Blocking firebase runs
    off the event loop; any failure is logged sanitized, never raised."""
    if not is_configured() or not tokens:
        return []
    try:
        return await asyncio.to_thread(_send_sync, tokens, title, body)
    except Exception as exc:
        _log.warning("push send failed (%s)", type(exc).__name__)
        return []
