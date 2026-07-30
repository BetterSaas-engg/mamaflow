"""How many mailboxes a user has connected, and whether they may add another.

This is the seam the mailbox cap is measured against. Phase 1 stores exactly
one mail credential per user (D38: `users.provider` plus one entry in the token
store, and connecting a different provider PURGES the old one). So the count
here is 0 or 1 today.

When `mail_connections` lands (the deferred D38 Phase 2, which is what makes
Pro/Family mean anything), only `connected_mailbox_count` changes — callers and
the cap policy stay as they are.
"""

import asyncio

from api.auth.token_store import get_token
from api.models.user import User
from api.services.entitlements import (
    can_connect_another_mailbox,
    mailbox_limit,
)


async def connected_mailbox_count(user: User) -> int:
    """Mailboxes currently connected for this user.

    Reads the credential store rather than assuming, because a user row can
    outlive its credential: a revoked app password or a Secret Manager purge
    leaves `users.provider` set with nothing behind it, and counting that as a
    used slot would wedge someone under their own cap.
    """
    token = await asyncio.to_thread(get_token, user.email, user.provider)
    return 1 if token else 0


async def mailbox_usage(user: User) -> tuple[int, int, bool]:
    """(connected, limit, can_add) for this user's tier."""
    connected = await connected_mailbox_count(user)
    limit = mailbox_limit(user.tier)
    return connected, limit, can_connect_another_mailbox(user.tier, connected)
