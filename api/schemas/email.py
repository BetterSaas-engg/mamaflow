from pydantic import BaseModel


class EmailPreview(BaseModel):
    message_id: str
    sender: str
    subject: str
    date: str
    body: str
