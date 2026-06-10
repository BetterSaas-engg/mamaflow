from fastapi import APIRouter, HTTPException, Query

from api.schemas.email import EmailPreview
from api.services.gmail_reader import fetch_recent_emails

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])


@router.get("/preview", response_model=list[EmailPreview])
async def preview_emails(email: str = Query(description="Authenticated user's email address")):
    try:
        emails = fetch_recent_emails(email)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return emails
