from pydantic import BaseModel


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
