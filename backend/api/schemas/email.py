from pydantic import BaseModel

from api.schemas.family_event import FamilyEvent


class EmailPreview(BaseModel):
    message_id: str
    sender: str
    subject: str
    date: str
    body: str
    pii_redacted: int = 0


class BlockedEmail(BaseModel):
    message_id: str
    sender: str
    subject: str
    date: str
    reason: str
    category: str | None
    list_status: str


class FilteredPreview(BaseModel):
    allowed: list[EmailPreview]
    blocked: list[BlockedEmail]
    unknown: list[EmailPreview]


class EmailExtraction(BaseModel):
    message_id: str
    sender: str
    subject: str
    date: str
    events: list[FamilyEvent]
    pii_redacted: int = 0


class ExtractionPreview(BaseModel):
    allowed: list[EmailExtraction]
    blocked: list[BlockedEmail]
    unknown: list[EmailExtraction]
    total_events: int
