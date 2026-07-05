"""Gmail sync endpoints.

All endpoints derive the user from the JWT (get_current_user) — no ?email=
query param. The fetch is metadata-first: senders are checked against the
blocklist before any body is pulled, so a blocked sender's body is never
fetched (AGENTS.md / D13). Blocking I/O is run off the event loop.
"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from api.auth.dependencies import get_current_user
from api.config.settings import settings
from api.db.session import get_db, get_session_factory
from api.models.user import User
from api.schemas.email import (
    EmailMetadata,
    ExtractionPreview,
    FilteredPreview,
    SyncStartResponse,
    SyncStatusResponse,
)
from api.services import sync_state
from api.services.ai_extractor import extract_events
from api.services.gmail_reader import fetch_message_bodies, fetch_recent_metadata
from api.services.items import existing_message_ids, persist_items
from api.services.privacy_pipeline import redact_pii
from api.services.sender_blocklist import is_blocked_sender

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])


def _blocked_entry(msg: dict, result) -> dict:
    return {
        "message_id": msg["message_id"],
        "sender": msg["sender"],
        "subject": msg["subject"],
        "date": msg["date"],
        "reason": result.reason,
        "category": result.category,
        "list_status": result.list_status,
    }


async def _classify(metadata: list[dict], db: AsyncSession):
    """Split scanned metadata into (passed, blocked) without fetching any body.

    `passed` carries each message dict plus its allowed/unknown list_status.
    """
    passed = []
    blocked = []
    for msg in metadata:
        result = await is_blocked_sender(msg["sender"], db)
        if result.list_status == "blocked":
            blocked.append(_blocked_entry(msg, result))
        else:
            passed.append((msg, result.list_status))
    return passed, blocked


@router.get("/preview", response_model=list[EmailMetadata])
async def preview_emails(user: User = Depends(get_current_user)):
    """Metadata-only list (no bodies fetched) of the last 30 days."""
    metadata = await asyncio.to_thread(fetch_recent_metadata, user.email)
    return metadata


@router.get("/preview-filtered", response_model=FilteredPreview)
async def preview_filtered(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    metadata = await asyncio.to_thread(fetch_recent_metadata, user.email)
    passed, blocked = await _classify(metadata, db)

    bodies = await asyncio.to_thread(
        fetch_message_bodies, user.email, [m["message_id"] for m, _ in passed]
    )

    allowed = []
    unknown = []
    for msg, status in passed:
        redaction = redact_pii(bodies.get(msg["message_id"], ""))
        entry = {**msg, "body": redaction.redacted_text, "pii_redacted": redaction.entities_found}
        (allowed if status == "allowed" else unknown).append(entry)

    return {"allowed": allowed, "blocked": blocked, "unknown": unknown}


@router.get("/extract", response_model=ExtractionPreview)
async def extract_emails(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Full pipeline: metadata → blocklist → (bodies for passers) → PII redaction
    → injection wrapper → Claude extraction → structured events."""
    metadata = await asyncio.to_thread(fetch_recent_metadata, user.email)
    passed, blocked = await _classify(metadata, db)

    bodies = await asyncio.to_thread(
        fetch_message_bodies, user.email, [m["message_id"] for m, _ in passed]
    )

    allowed = []
    unknown = []
    total_events = 0
    for msg, status in passed:
        redaction = redact_pii(bodies.get(msg["message_id"], ""))
        extraction = await asyncio.to_thread(
            extract_events,
            redaction.redacted_text,
            msg["subject"],
            msg["sender"],
            msg["message_id"],
            msg["date"],
        )
        entry = {
            "message_id": msg["message_id"],
            "sender": msg["sender"],
            "subject": msg["subject"],
            "date": msg["date"],
            "events": [e.model_dump() for e in extraction.events],
            "pii_redacted": redaction.entities_found,
        }
        total_events += len(extraction.events)
        (allowed if status == "allowed" else unknown).append(entry)

    return {
        "allowed": allowed,
        "blocked": blocked,
        "unknown": unknown,
        "total_events": total_events,
    }


async def _run_sync_job(
    user_id: uuid.UUID,
    user_email: str,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The background sync: fetch → blocklist → incremental skip → redact →
    extract → persist. Opens its own session (the request's is closed by now).
    Reports progress/outcome via sync_state; errors are sanitized."""
    try:
        async with session_factory() as db:
            user = await db.get(User, user_id)
            if user is None:
                sync_state.fail(user_id, "user not found")
                return

            metadata = await asyncio.to_thread(fetch_recent_metadata, user_email)
            passed, blocked = await _classify(metadata, db)

            # Incremental: drop already-synced messages BEFORE body fetch and
            # extraction — dedup after the Claude call would still spend tokens.
            already = await existing_message_ids(
                db, user_id, [m["message_id"] for m, _ in passed]
            )
            new_passed = [
                (m, s) for m, s in passed if m["message_id"] not in already
            ]

            bodies = await asyncio.to_thread(
                fetch_message_bodies,
                user_email,
                [m["message_id"] for m, _ in new_passed],
            )

            sync_state.progress(
                user_id,
                messages_scanned=len(metadata),
                to_process=len(new_passed),
                processed=0,
                items_created=0,
            )

            items_created = 0
            for _i, (msg, _status) in enumerate(new_passed):
                redaction = redact_pii(bodies.get(msg["message_id"], ""))
                extraction = await asyncio.to_thread(
                    extract_events,
                    redaction.redacted_text,
                    msg["subject"],
                    msg["sender"],
                    msg["message_id"],
                    msg["date"],
                )
                saved = await persist_items(db, user, msg["message_id"], extraction.events)
                items_created += len(saved)
                sync_state.progress(
                    user_id,
                    messages_scanned=len(metadata),
                    to_process=len(new_passed),
                    processed=_i + 1,
                    items_created=items_created,
                )

            sync_state.finish(
                user_id,
                messages_scanned=len(metadata),
                blocked=len(blocked),
                processed=len(new_passed),
                items_created=items_created,
            )
    except Exception:
        # Full detail to server logs; only a sanitized message to the client.
        _log.exception("sync failed for user %s", user_id)
        sync_state.fail(user_id, "Sync failed. Try again.")


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
    background.add_task(_run_sync_job, user.id, user.email, session_factory)
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
