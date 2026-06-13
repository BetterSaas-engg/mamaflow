from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.session import get_db
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
            allowed.append(msg)
        else:
            unknown.append(msg)

    return {"allowed": allowed, "blocked": blocked, "unknown": unknown}
