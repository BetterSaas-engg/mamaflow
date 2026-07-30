"""Account deletion: soft-delete the user's data + revoke the Gmail token.

Deletion is soft (deleted_at), per the locked AGENTS.md rule. Gmail access is
truly severed by revoking the token at Google. Revocation is best-effort — a
failure never blocks the local delete, and no token value is ever logged."""

import asyncio
import datetime
import logging

import httpx
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import token_store
from api.models.device import Device
from api.models.item import Item
from api.models.mail_connection import MailConnection
from api.models.user import User
from api.services.mail_connections import list_connections

_log = logging.getLogger(__name__)

_GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"


def revoke_gmail_token(credentials: dict) -> None:
    """Best-effort revoke at Google. Revoking the refresh token invalidates its
    derived access tokens. Never raises; never logs the token value."""
    token = credentials.get("refresh_token") or credentials.get("token")
    if not token:
        return
    try:
        httpx.post(_GOOGLE_REVOKE_URL, data={"token": token}, timeout=10)
    except Exception as exc:
        _log.warning("gmail token revoke failed (%s)", type(exc).__name__)


async def delete_account(db: AsyncSession, user: User) -> None:
    """Soft-delete the user + their items + devices (one commit), then revoke
    and drop the Gmail token."""
    now = datetime.datetime.now(datetime.UTC)

    # Read the mailboxes BEFORE soft-deleting them — afterwards
    # list_connections filters them out and their credentials would be
    # unreachable, i.e. leaked.
    connections = await list_connections(db, user.id)

    await db.execute(
        update(Item).where(Item.user_id == user.id, Item.deleted_at.is_(None))
        .values(deleted_at=now)
    )
    await db.execute(
        update(Device).where(Device.user_id == user.id, Device.deleted_at.is_(None))
        .values(deleted_at=now)
    )
    await db.execute(
        update(MailConnection)
        .where(
            MailConnection.user_id == user.id,
            MailConnection.deleted_at.is_(None),
        )
        .values(deleted_at=now)
    )
    user.deleted_at = now
    await db.commit()

    # With the secret-manager backend, get/delete are blocking gRPC calls —
    # keep them off the event loop, like the revoke in between.
    # Google: revoke at Google, then delete the stored token. IMAP providers
    # have no server-side revoke for app passwords — the frontend deletion copy
    # tells the user to revoke the app password at their provider.
    # Every mailbox, not just the identity address. Since D44 a user can hold
    # several connections whose emails differ from users.email, and purging
    # only the identity address would leave those credentials live after the
    # account was deleted — the D38 stale-credential class, at the worst
    # possible moment.
    for connection in connections:
        creds = await asyncio.to_thread(
            token_store.get_token, connection.email, connection.provider
        )
        if creds is not None and connection.provider == "google":
            try:
                await asyncio.to_thread(revoke_gmail_token, creds)
            except Exception as exc:  # defensive: revoke_gmail_token shouldn't raise
                _log.warning("gmail token revoke raised (%s)", type(exc).__name__)
        await asyncio.to_thread(
            token_store.delete_all_tokens, connection.email
        )

    # Backstop for the identity address itself: a credential can predate the
    # connections table, or outlive a mailbox the user disconnected earlier.
    creds = await asyncio.to_thread(token_store.get_token, user.email)
    if creds is not None:
        try:
            await asyncio.to_thread(revoke_gmail_token, creds)
        except Exception as exc:
            _log.warning("gmail token revoke raised (%s)", type(exc).__name__)
    # Purge credentials under EVERY provider — not just the current one — so
    # nothing survives account deletion, regardless of which providers the
    # account passed through over its life (D4 credential lifecycle).
    await asyncio.to_thread(token_store.delete_all_tokens, user.email)
