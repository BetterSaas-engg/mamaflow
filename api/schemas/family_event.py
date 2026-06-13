"""Locked output schema for Claude extraction — doubles as injection defense.

Claude is instructed to return ONLY a JSON array matching this schema.
A fixed output format limits what a prompt-injection payload can achieve
even if it partially succeeds.
"""

from pydantic import BaseModel


class FamilyEvent(BaseModel):
    event_title: str
    date: str | None = None
    time: str | None = None
    location: str | None = None
    child_name: str | None = None
    event_type: str | None = None  # e.g. "school", "medical", "sports", "playdate", "camp"
    source_sender: str | None = None


class ExtractionResponse(BaseModel):
    events: list[FamilyEvent]
