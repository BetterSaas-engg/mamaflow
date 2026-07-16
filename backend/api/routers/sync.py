"""Gmail sync endpoints.

All endpoints derive the user from the JWT (get_current_user) — no ?email=
query param. The fetch is metadata-first: senders are checked against the
blocklist before any body is pulled, so a blocked sender's body is never
fetched (AGENTS.md / D13). Blocking I/O is run off the event loop.
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.auth.dependencies import get_current_user
from api.config.settings import settings
from api.db.session import get_session_factory
from api.models.user import User
from api.schemas.email import SyncStartResponse, SyncStatusResponse
from api.services import sync_state
from api.services.sync_runner import run_sync_job

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])


@router.post("", response_model=SyncStartResponse, status_code=202)
async def start_sync(
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory),
):
    """Kick off a background sync for the authed user; poll GET /sync/status.

    Rate-limited per user: each sync is a full 30-day metadata scan, so
    completed syncs are separated by a cooldown (429 + Retry-After)."""
    outcome, retry_after = sync_state.try_start(
        user.id, cooldown_seconds=settings.sync_cooldown_seconds
    )
    if outcome == "already_running":
        return SyncStartResponse(status="already_running")
    if outcome == "cooldown":
        raise HTTPException(
            status_code=429,
            detail="Synced recently — try again in a minute.",
            headers={"Retry-After": str(max(1, int(retry_after)))},
        )
    background.add_task(run_sync_job, user.id, user.email, session_factory)
    return SyncStartResponse(status="started")


@router.get("/status", response_model=SyncStatusResponse)
async def get_sync_status(user: User = Depends(get_current_user)):
    state = sync_state.get_state(user.id)
    return SyncStatusResponse(
        status=state.status,
        messages_scanned=state.messages_scanned,
        blocked=state.blocked,
        processed=state.processed,
        to_process=state.to_process,
        items_created=state.items_created,
        error=state.error,
    )
