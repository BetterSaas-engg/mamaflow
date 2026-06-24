"""API schemas for the items endpoints.

The DB stores event_date/event_time; the API contract uses date/time
(matching FamilyItem). item_to_read() maps between them.
"""

from typing import Literal

from pydantic import BaseModel


class ItemRead(BaseModel):
    id: str
    item_type: str
    status: str
    event_title: str | None = None
    action_required: str | None = None
    date: str | None = None
    time: str | None = None
    location: str | None = None
    child_name: str | None = None
    event_type: str | None = None
    source_sender: str | None = None
    source_email_link: str | None = None


class ItemListResponse(BaseModel):
    items: list[ItemRead]


class ItemUpdate(BaseModel):
    status: Literal["done", "dismissed"]


def item_to_read(item) -> ItemRead:
    return ItemRead(
        id=str(item.id),
        item_type=item.item_type,
        status=item.status,
        event_title=item.event_title,
        action_required=item.action_required,
        date=item.event_date,
        time=item.event_time,
        location=item.location,
        child_name=item.child_name,
        event_type=item.event_type,
        source_sender=item.source_sender,
        source_email_link=item.source_email_link,
    )
