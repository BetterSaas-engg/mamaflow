"""Account deletion: soft-delete the user's data + revoke the Gmail token.

Deletion is soft (deleted_at), per the locked AGENTS.md rule. Gmail access is
truly severed by revoking the token at Google. Revocation is best-effort — a
failure never blocks the local delete, and no token value is ever logged."""

import asyncio
import datetime
import uuid
import logging

import httpx
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import token_store
from api.models.device import Device
from api.models.item import Item
from api.models.mail_connection import MailConnection
from api.models.user import User
from api.services.households import dissolve_or_leave
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
    """Soft-delete the user + their items + devices, and destroy every mailbox
    credential the account held.

    Credentials are purged BEFORE the rows are soft-deleted. Ordering matters:
    once a connection row is marked deleted, nothing queries it again, so a
    credential we failed to destroy would be invisible forever. Purging first
    means a failure leaves that row live and therefore still discoverable —
    the same reasoning as remove_connection.
    """
    now = datetime.datetime.now(datetime.UTC)

    # Read the mailboxes first: after the soft-delete they are filtered out of
    # every query, and their credentials would be unreachable, i.e. leaked.
    connections = await list_connections(db, user.id)

    # Each mailbox is isolated. The credential store raises on any transient
    # Secret Manager fault (quota, outage, permissions), and one throw used to
    # abandon the whole loop, leaving the remaining mailboxes' secrets alive.
    # Deletion is the user's right and must not be blocked by a store blip, so
    # a failure is logged loudly and skipped — never re-raised.
    purged: list[uuid.UUID] = []
    for connection in connections:
        try:
            creds = await asyncio.to_thread(
                token_store.get_token, connection.email, connection.provider
            )
            if creds is not None and connection.provider == "google":
                try:
                    await asyncio.to_thread(revoke_gmail_token, creds)
                except Exception as exc:  # defensive: shouldn't raise
                    _log.warning("gmail token revoke raised (%s)", type(exc).__name__)
            await asyncio.to_thread(token_store.delete_all_tokens, connection.email)
            purged.append(connection.id)
        except Exception as exc:
            # Ids only, never the address (audit log rule). Left live on
            # purpose so a cleanup pass can still find it.
            _log.error(
                "account delete: could not purge credential for user %s "
                "connection %s (%s) — LEFT LIVE FOR RETRY",
                user.id,
                connection.id,
                type(exc).__name__,
            )

    # Sever household ties BEFORE the row is marked deleted, or a later
    # sign-in reactivates the row with its membership intact and restores
    # sharing without consent.
    await dissolve_or_leave(db, user)

    await db.execute(
        update(Item).where(Item.user_id == user.id, Item.deleted_at.is_(None))
        .values(deleted_at=now)
    )
    await db.execute(
        update(Device).where(Device.user_id == user.id, Device.deleted_at.is_(None))
        .values(deleted_at=now)
    )
    if purged:
        await db.execute(
            update(MailConnection)
            .where(
                MailConnection.user_id == user.id,
                MailConnection.id.in_(purged),
                MailConnection.deleted_at.is_(None),
            )
            .values(deleted_at=now)
        )
    user.deleted_at = now
    await db.commit()

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
