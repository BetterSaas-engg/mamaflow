"""Hourly background Gmail sync per signed-in user (spec 2026-07-15).

Reuses the manual sync's job and state gate — auto and manual syncs can
never double-run, and the manual cooldown carries over. Users without a
stored Gmail token are skipped (normal until A1/Secret Manager is live).
"""

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.auth.token_store import get_token
from api.config.settings import settings
from api.models.user import User
from api.services import sync_state
from api.services.sync_runner import run_sync_job

_log = logging.getLogger(__name__)


async def auto_sync_tick(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """One hourly pass: sync every eligible user, sequentially. Per-user
    try/except — one user's failure never stops the pass (types-only logs)."""
    async with session_factory() as db:
        rows = await db.execute(
            select(User.id, User.email).where(User.deleted_at.is_(None))
        )
        candidates = [(row.id, row.email) for row in rows]

    for user_id, email in candidates:
        try:
            # Secret Manager reads are blocking network I/O — off the loop.
            token = await asyncio.to_thread(get_token, email)
            if token is None:
                _log.debug("auto-sync: no stored token for user %s", user_id)
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
