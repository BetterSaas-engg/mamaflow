from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db
from api.schemas.email import EmailPreview, ExtractionPreview, FilteredPreview
from api.services.ai_extractor import extract_events
from api.services.gmail_reader import fetch_recent_emails
from api.services.privacy_pipeline import redact_pii
from api.services.sender_blocklist import is_blocked_sender

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])


@router.get("/preview", response_model=list[EmailPreview])
async def preview_emails(email: str = Query(description="Authenticated user's email address")):
    try:
        emails = fetch_recent_emails(email)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return emails


@router.get("/preview-filtered", response_model=FilteredPreview)
async def preview_filtered(
    email: str = Query(description="Authenticated user's email address"),
    db: AsyncSession = Depends(get_db),
):
    try:
        emails = fetch_recent_emails(email)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    allowed = []
    blocked = []
    unknown = []

    for msg in emails:
        result = await is_blocked_sender(msg["sender"], db)

        if result.list_status == "blocked":
            blocked.append({
                "message_id": msg["message_id"],
                "sender": msg["sender"],
                "subject": msg["subject"],
                "date": msg["date"],
                "reason": result.reason,
                "category": result.category,
                "list_status": result.list_status,
            })
        elif result.list_status == "allowed":
            redaction = redact_pii(msg.get("body", ""))
            allowed.append({**msg, "body": redaction.redacted_text, "pii_redacted": redaction.entities_found})
        else:
            redaction = redact_pii(msg.get("body", ""))
            unknown.append({**msg, "body": redaction.redacted_text, "pii_redacted": redaction.entities_found})

    return {"allowed": allowed, "blocked": blocked, "unknown": unknown}


@router.get("/extract", response_model=ExtractionPreview)
async def extract_emails(
    email: str = Query(description="Authenticated user's email address"),
    db: AsyncSession = Depends(get_db),
):
    """Full pipeline: fetch → Layer 1 blocklist → Layer 2 PII redaction →
    Layer 3 injection wrapper → Claude extraction → structured events."""
    try:
        emails = fetch_recent_emails(email)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    allowed = []
    blocked = []
    unknown = []
    total_events = 0

    for msg in emails:
        result = await is_blocked_sender(msg["sender"], db)

        if result.list_status == "blocked":
            blocked.append({
                "message_id": msg["message_id"],
                "sender": msg["sender"],
                "subject": msg["subject"],
                "date": msg["date"],
                "reason": result.reason,
                "category": result.category,
                "list_status": result.list_status,
            })
            continue

        redaction = redact_pii(msg.get("body", ""))
        extraction = extract_events(redaction.redacted_text, msg["subject"], msg["sender"])

        entry = {
            "message_id": msg["message_id"],
            "sender": msg["sender"],
            "subject": msg["subject"],
            "date": msg["date"],
            "events": [e.model_dump() for e in extraction.events],
            "pii_redacted": redaction.entities_found,
        }
        total_events += len(extraction.events)

        if result.list_status == "allowed":
            allowed.append(entry)
        else:
            unknown.append(entry)

    return {
        "allowed": allowed,
        "blocked": blocked,
        "unknown": unknown,
        "total_events": total_events,
    }
