"""Locked output schema for Claude extraction — doubles as injection defense.

Claude is instructed to return ONLY a JSON array matching this schema.
A fixed output format limits what a prompt-injection payload can achieve
even if it partially succeeds.

An item can be an "event" (has a date/time) or a standalone "action"
(a to-do with no date, e.g. a registration link). An event may also
carry an action_required (e.g. "call to confirm").
"""

from typing import Literal

from pydantic import BaseModel, field_validator

# Must stay in sync with the anyOf enum in content_wrapper._EXTRACTION_JSON_SCHEMA.
EVENT_TYPES = (
    "school", "medical", "sports", "playdate",
    "camp", "birthday", "recital", "other",
)


class FamilyItem(BaseModel):
    item_type: Literal["event", "action"]
    event_title: str | None = None
    action_required: str | None = None
    date: str | None = None
    time: str | None = None
    location: str | None = None
    child_name: str | None = None
    event_type: (
        Literal[
            "school", "medical", "sports", "playdate",
            "camp", "birthday", "recital", "other",
        ]
        | None
    ) = None

    @field_validator("event_type", mode="before")
    @classmethod
    def _unknown_event_type_becomes_other(cls, v):
        # The tool schema constrains the vocabulary, but if it ever drifts or
        # is bypassed, an unexpected value must degrade to "other" — never
        # fail validation and drop the whole message's events (2026-07-15).
        if v is None or v in EVENT_TYPES:
            return v
        return "other"
    source_sender: str | None = None
    source_email_link: str | None = None


# Keep the old name as an alias so existing imports don't break
FamilyEvent = FamilyItem


class ExtractionResponse(BaseModel):
    events: list[FamilyItem]
