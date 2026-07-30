"""Hourly background mail sync per signed-in user (spec 2026-07-15).

Reuses the manual sync's job and state gate — auto and manual syncs can
never double-run, and the manual cooldown carries over. Users without a
stored credential are skipped (normal until A1/Secret Manager is live).
"""

import asyncio
import datetime
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.config.settings import settings
from api.models.user import User
from api.services import sync_state
from api.services.mail_connections import connection_count
from api.services.sync_runner import run_sync_job

_log = logging.getLogger(__name__)


async def auto_sync_tick(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """One hourly pass: sync every eligible user, sequentially. Per-user
    try/except — one user's failure never stops the pass (types-only logs)."""
    async with session_factory() as db:
        query = select(User.id, User.email, User.provider).where(
            User.deleted_at.is_(None)
        )
        # Dormant accounts cost money hourly forever otherwise: the tick used
        # to bill every user who ever signed up, whether or not they ever came
        # back. Skipping is a pause, not a tombstone — one authenticated
        # request re-arms the account on the next tick.
        if settings.auto_sync_dormant_days > 0:
            cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
                days=settings.auto_sync_dormant_days
            )
            query = query.where(User.last_seen_at >= cutoff)
        rows = await db.execute(query)
        candidates = [(row.id, row.email, row.provider) for row in rows]

    for user_id, email, provider in candidates:
        try:
            # Eligibility is "has at least one mailbox", not "the identity
            # address has a credential" (D44): a user's mailboxes can all be
            # addresses other than users.email, and the old check skipped them
            # entirely. Per-mailbox credential problems are handled inside the
            # job, which keeps the healthy mailboxes syncing.
            async with session_factory() as db:
                mailboxes = await connection_count(db, user_id)
            if not mailboxes:
                _log.debug("auto-sync: no connected mailbox for user %s", user_id)
                continue
            outcome, _retry = sync_state.try_start(
                user_id, cooldown_seconds=settings.sync_cooldown_seconds
            )
            if outcome != "started":
                continue
            await run_sync_job(user_id, email, session_factory)
        except Exception as exc:
            _log.warning(
                "auto-sync failed for user %s (%s)", user_id, type(exc).__name__
            )
