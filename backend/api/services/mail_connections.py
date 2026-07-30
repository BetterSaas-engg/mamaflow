"""Managing the mailboxes a user has connected.

This is where the D44 cap stops being a policy and starts being enforced:
before this table existed, connecting a mailbox REPLACED the previous one, so
"free = 1" was true by construction and pro/family were unreachable.

Credentials never live in the DB (D4). A connection row records that a mailbox
is linked; the secret stays in the credential store keyed by (email, provider).
Removing a connection must therefore delete both, or a revoked mailbox would
leave a live app password behind — the D38 audit finding, which the old
purge-on-switch used to handle and explicit disconnect must now handle instead.
"""

import asyncio
import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.token_store import delete_other_tokens, delete_token
from api.models.mail_connection import MailConnection
from api.models.user import User
from api.services.entitlements import can_connect_another_mailbox, mailbox_limit


class MailboxLimitReached(Exception):
    """The user's tier does not allow another mailbox."""

    def __init__(self, tier: str, limit: int) -> None:
        super().__init__(f"{tier} plan allows {limit} mailbox(es)")
        self.tier = tier
        self.limit = limit


def _normalize(email: str) -> str:
    return email.strip().lower()


async def list_connections(db: AsyncSession, user_id) -> list[MailConnection]:
    """This user's live mailboxes, oldest first (their first mailbox stays
    first in the UI rather than jumping around)."""
    rows = await db.execute(
        select(MailConnection)
        .where(
            MailConnection.user_id == user_id,
            MailConnection.deleted_at.is_(None),
        )
        .order_by(MailConnection.created_at)
    )
    return list(rows.scalars())


async def connection_count(db: AsyncSession, user_id) -> int:
    return len(await list_connections(db, user_id))


async def get_connection(
    db: AsyncSession, user_id, connection_id: uuid.UUID
) -> MailConnection | None:
    """Scoped to the user on purpose — never look a connection up by id alone,
    or one user could disconnect another's mailbox."""
    rows = await db.execute(
        select(MailConnection).where(
            MailConnection.id == connection_id,
            MailConnection.user_id == user_id,
            MailConnection.deleted_at.is_(None),
        )
    )
    return rows.scalar_one_or_none()


async def ensure_connection(
    db: AsyncSession, user: User, provider: str, email: str
) -> MailConnection:
    """Record that `email` is connected for this user, enforcing the tier cap.

    Idempotent for a mailbox that is already connected: re-authenticating an
    existing mailbox (a rotated app password, a fresh OAuth grant) must never
    be blocked by the cap, only ADDING a new one. Reconnecting an address that
    was previously disconnected revives the tombstoned row instead of failing
    the partial unique index.
    """
    normalized = _normalize(email)
    # D38's guarantee, re-scoped for multi-mailbox: no address may keep a live
    # credential under a provider it is no longer connected through. Before the
    # table this was "purge every OTHER provider for the user's identity
    # email"; the right scope now is the MAILBOX being connected, which leaves
    # the user's other mailboxes alone. Unconditional, so it also covers a
    # credential that exists with no row behind it (a pre-table leftover) —
    # relying on the row to spot the switch would miss exactly that case.
    await asyncio.to_thread(delete_other_tokens, normalized, provider)
    existing = await db.execute(
        select(MailConnection).where(
            MailConnection.user_id == user.id,
            MailConnection.email == normalized,
        )
    )
    row = existing.scalars().first()
    if row is not None and row.deleted_at is None:
        if row.provider != provider:
            row.provider = provider
            await db.commit()
        return row

    # A genuinely new mailbox — this is the only path the cap applies to.
    current = await connection_count(db, user.id)
    if not can_connect_another_mailbox(user.tier, current):
        raise MailboxLimitReached(user.tier, mailbox_limit(user.tier))

    if row is not None:  # revive a previously disconnected mailbox
        row.deleted_at = None
        row.provider = provider
        await db.commit()
        return row

    row = MailConnection(user_id=user.id, provider=provider, email=normalized)
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        # Lost a concurrent add of the same mailbox; the winner's row is the
        # one to use.
        await db.rollback()
        winner = await db.execute(
            select(MailConnection).where(
                MailConnection.user_id == user.id,
                MailConnection.email == normalized,
                MailConnection.deleted_at.is_(None),
            )
        )
        found = winner.scalar_one_or_none()
        if found is None:
            raise
        return found
    return row


async def remove_connection(
    db: AsyncSession, user: User, connection: MailConnection
) -> None:
    """Disconnect a mailbox: soft-delete the row AND destroy its credential.

    The credential goes first. If the row were cleared first and the token
    delete then failed, we would be left with a live app password nobody can
    see or manage — exactly the stale-credential class the D38 audit flagged.
    """
    await asyncio.to_thread(delete_token, connection.email, connection.provider)
    connection.deleted_at = datetime.datetime.now(datetime.timezone.utc)
    await db.commit()


async def mailbox_usage(db: AsyncSession, user: User) -> tuple[int, int, bool]:
    """(connected, limit, can_add) for this user's tier.

    Counted from live connection rows. Note the deliberate change from the
    pre-table behaviour, where the count came from the credential store and a
    revoked app password silently freed a slot: a broken mailbox now still
    occupies its slot until the user disconnects it. That is more predictable —
    the slot is released by an action the user can see and undo, not by a
    failure happening somewhere they can't observe.
    """
    connected = await connection_count(db, user.id)
    limit = mailbox_limit(user.tier)
    return connected, limit, can_connect_another_mailbox(user.tier, connected)
