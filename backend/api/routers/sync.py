"""Gmail sync endpoints.

All endpoints derive the user from the JWT (get_current_user) — no ?email=
query param. The fetch is metadata-first: senders are checked against the
blocklist before any body is pulled, so a blocked sender's body is never
fetched (AGENTS.md / D13). Blocking I/O is run off the event loop.
"""

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth.dependencies import get_current_user
from api.db.session import get_db
from api.models.user import User
from api.schemas.email import (
    EmailMetadata,
    ExtractionPreview,
    FilteredPreview,
    SyncResult,
)
from api.services.ai_extractor import extract_events
from api.services.gmail_reader import fetch_message_bodies, fetch_recent_metadata
from api.services.items import persist_items
from api.services.privacy_pipeline import redact_pii
from api.services.sender_blocklist import is_blocked_sender

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
            extract_events, redaction.redacted_text, msg["subject"], msg["sender"], msg["message_id"]
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


@router.post("", response_model=SyncResult)
async def run_sync(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch → blocklist → redact → extract → persist for the authed user.

    Idempotent per message (persist_items skips already-synced messages)."""
    metadata = await asyncio.to_thread(fetch_recent_metadata, user.email)
    passed, blocked = await _classify(metadata, db)

    bodies = await asyncio.to_thread(
        fetch_message_bodies, user.email, [m["message_id"] for m, _ in passed]
    )

    items_created = 0
    for msg, _status in passed:
        redaction = redact_pii(bodies.get(msg["message_id"], ""))
        extraction = await asyncio.to_thread(
            extract_events, redaction.redacted_text, msg["subject"], msg["sender"], msg["message_id"]
        )
        saved = await persist_items(db, user, msg["message_id"], extraction.events)
        items_created += len(saved)

    return SyncResult(
        messages_scanned=len(metadata),
        blocked=len(blocked),
        processed=len(passed),
        items_created=items_created,
    )
