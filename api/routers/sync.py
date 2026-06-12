from fastapi import APIRouter, HTTPException, Query

from api.schemas.email import EmailPreview, FilteredPreview
from api.services.gmail_reader import fetch_recent_emails
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
async def preview_filtered(email: str = Query(description="Authenticated user's email address")):
    try:
        emails = fetch_recent_emails(email)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    kept = []
    blocked = []

    for msg in emails:
        is_blocked, reason, category = is_blocked_sender(msg["sender"])
        if is_blocked:
            blocked.append({
                "message_id": msg["message_id"],
                "sender": msg["sender"],
                "subject": msg["subject"],
                "date": msg["date"],
                "reason": reason,
                "category": category,
            })
        else:
            kept.append(msg)

    return {"kept": kept, "blocked": blocked}
