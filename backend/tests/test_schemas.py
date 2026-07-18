"""Schema-level contracts (2026-07-18 audit): the event_type vocabulary is
enforced in Pydantic (the DB has no CHECK on it), and egress enums are typed.

FamilyItem is the single validation layer for untrusted Claude tool output —
but an unexpected event_type must degrade to "other", never fail the whole
message's extraction (the 2026-07-15 lesson: schema drift silently killed
every sync)."""

import pytest
from pydantic import ValidationError

from api.schemas.family_event import FamilyItem
from api.schemas.item import ItemRead


def test_family_item_accepts_known_event_types():
    for value in ("school", "medical", "sports", "playdate", "camp",
                  "birthday", "recital", "other", None):
        assert FamilyItem(item_type="event", event_type=value).event_type == value


def test_family_item_coerces_unknown_event_type_to_other():
    item = FamilyItem(item_type="event", event_type="crypto-deals")
    assert item.event_type == "other"


def test_family_item_coerces_non_string_event_type_to_other():
    assert FamilyItem(item_type="event", event_type=42).event_type == "other"


def _read_kwargs(**overrides):
    base = {"id": "x", "item_type": "event", "status": "open"}
    base.update(overrides)
    return base


def test_item_read_accepts_db_enforced_values():
    for item_type in ("event", "action"):
        for status in ("open", "done", "dismissed"):
            ItemRead(**_read_kwargs(item_type=item_type, status=status))


def test_item_read_rejects_unknown_item_type_and_status():
    with pytest.raises(ValidationError):
        ItemRead(**_read_kwargs(item_type="banner-ad"))
    with pytest.raises(ValidationError):
        ItemRead(**_read_kwargs(status="weird"))
