"""Locked output schema for Claude extraction — doubles as injection defense.

Claude is instructed to return ONLY a JSON array matching this schema.
A fixed output format limits what a prompt-injection payload can achieve
even if it partially succeeds.

An item can be an "event" (has a date/time) or a standalone "action"
(a to-do with no date, e.g. a registration link). An event may also
carry an action_required (e.g. "call to confirm").
"""

from typing import Literal

from pydantic import BaseModel


class FamilyItem(BaseModel):
    item_type: Literal["event", "action"]
    event_title: str | None = None
    action_required: str | None = None
    date: str | None = None
    time: str | None = None
    location: str | None = None
    child_name: str | None = None
    event_type: str | None = None  # e.g. "school", "medical", "sports", "playdate", "camp"
    source_sender: str | None = None
    source_email_link: str | None = None


# Keep the old name as an alias so existing imports don't break
FamilyEvent = FamilyItem


class ExtractionResponse(BaseModel):
    events: list[FamilyItem]
