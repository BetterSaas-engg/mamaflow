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
from api.models.user import User

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

    await db.execute(
        update(Item).where(Item.user_id == user.id, Item.deleted_at.is_(None))
        .values(deleted_at=now)
    )
    await db.execute(
        update(Device).where(Device.user_id == user.id, Device.deleted_at.is_(None))
        .values(deleted_at=now)
    )
    user.deleted_at = now
    await db.commit()

    creds = token_store.get_token(user.email)
    if creds is not None:
        try:
            await asyncio.to_thread(revoke_gmail_token, creds)
        except Exception as exc:  # defensive: revoke_gmail_token shouldn't raise
            _log.warning("gmail token revoke raised (%s)", type(exc).__name__)
    token_store.delete_token(user.email)
