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
from api.services.households import members, plan_owner, plan_tier


class MailboxAlreadyConnected(Exception):
    """This mailbox is already connected to a different account."""

    def __init__(self, email: str) -> None:
        super().__init__("mailbox already connected to another account")
        self.email = email


class MailboxLimitReached(Exception):
    """The user's tier does not allow another mailbox."""

    def __init__(self, tier: str, limit: int) -> None:
        super().__init__(f"{tier} plan allows {limit} mailbox(es)")
        self.tier = tier
        self.limit = limit


def _normalize(email: str) -> str:
    return email.strip().lower()


async def _purge_superseded_credentials(email: str, provider: str) -> None:
    """Destroy any credential this address still holds under a DIFFERENT
    provider.

    D38's guarantee, re-scoped for multi-mailbox: no address may keep a live
    credential under a provider it is no longer connected through. Before the
    table this was "purge every other provider for the user's identity email";
    the right scope now is the MAILBOX, which leaves the user's other mailboxes
    alone.

    Only ever called once the connection is actually established — a request we
    are going to reject must not destroy anything.
    """
    await asyncio.to_thread(delete_other_tokens, email, provider)


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
    """Mailboxes belonging to THIS user.

    Deliberately per-user and left that way: auto_sync uses it to answer "does
    this user have a mailbox to sync", where household-scoping would make a
    mailbox-less member look syncable and waste a run. The cap uses
    plan_connection_count instead.
    """
    return len(await list_connections(db, user_id))


async def plan_connection_count(db: AsyncSession, user: User) -> int:
    """Mailboxes across the whole PLAN — every household member, or just this
    user when they are solo.

    The cap is plan-wide (D47: Family is 3 shared, not 3 each). Counting
    per-user while reading a household-scoped limit gave a Family household 3
    mailboxes EACH — twice what the tier is priced to serve.
    """
    owner = await plan_owner(db, user)
    if owner.household_id is None:
        return await connection_count(db, user.id)
    member_ids = [m.id for m in await members(db, owner.household_id)]
    if not member_ids:
        return await connection_count(db, user.id)
    rows = await db.execute(
        select(MailConnection.id).where(
            MailConnection.user_id.in_(member_ids),
            MailConnection.deleted_at.is_(None),
        )
    )
    return len(list(rows))


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
            await _purge_superseded_credentials(normalized, provider)
        return row

    # One live connection per address, across ALL users. The credential store
    # is keyed globally by (email, provider) with no user in the key, so two
    # accounts connecting the same address share one secret: the second connect
    # silently overwrote the first's credential, and either party disconnecting
    # destroyed it for both — leaving the other with a mailbox that still shows
    # as connected, still occupies a cap slot, and can no longer sync. Refuse
    # instead. (Genuinely shared family mailboxes are the household feature's
    # job, not two independent connections fighting over one secret.)
    taken = await db.execute(
        select(MailConnection.id).where(
            MailConnection.email == normalized,
            MailConnection.user_id != user.id,
            MailConnection.deleted_at.is_(None),
        )
    )
    if taken.first() is not None:
        raise MailboxAlreadyConnected(normalized)

    # A genuinely new mailbox — this is the only path the cap applies to.
    # Deliberately BEFORE any credential purge: a rejected request must leave
    # the world untouched. Purging first meant an over-cap attempt on a shared
    # address destroyed a live credential and then 402'd.
    #
    # Lock the user row first: count-then-insert is otherwise a TOCTOU, and two
    # concurrent adds of DIFFERENT addresses could both read "under the cap"
    # and both commit. (The unique index only catches the same-address race.)
    # No-op on SQLite, which serializes writes anyway.
    await db.execute(
        select(User.id).where(User.id == user.id).with_for_update()
    )
    current = await plan_connection_count(db, user)
    tier = await plan_tier(db, user)
    if not can_connect_another_mailbox(tier, current):
        raise MailboxLimitReached(tier, mailbox_limit(tier))

    if row is not None:  # revive a previously disconnected mailbox
        row.deleted_at = None
        row.provider = provider
        await db.commit()
        await _purge_superseded_credentials(normalized, provider)
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
    await _purge_superseded_credentials(normalized, provider)
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
    connected = await plan_connection_count(db, user)
    # One question, one answer: plan_tier resolves the household and any
    # override, so the number shown and the number enforced cannot disagree.
    tier = await plan_tier(db, user)
    limit = mailbox_limit(tier)
    return connected, limit, can_connect_another_mailbox(tier, connected)
