"""Date-format handling in extraction (ISO YYYY-MM-DD contract).

The items date-range filter compares ISO strings lexicographically, so every
event date must be YYYY-MM-DD. Two layers enforce it:
  1. The prompt instructs Claude (with the email's Date header for reference).
  2. normalize_item_date() is the deterministic backstop for prose dates.
Anthropic client is mocked — never hits the live API (testing skill).
"""

from unittest.mock import MagicMock

from api.services import ai_extractor
from api.services.ai_extractor import normalize_item_date
from api.services.content_wrapper import build_extraction_prompt, wrap_untrusted_content

EMAIL_DATE = "Wed, 2 Jul 2026 10:00:00 -0400"


# --- normalize_item_date (deterministic backstop) ---


def test_iso_date_passes_through():
    assert normalize_item_date("2026-07-05", EMAIL_DATE) == "2026-07-05"


def test_prose_date_with_ordinal_and_weekday_normalizes():
    assert normalize_item_date("July 5th (Saturday)", EMAIL_DATE) == "2026-07-05"


def test_prose_date_with_explicit_year_normalizes():
    assert normalize_item_date("July 5, 2026", EMAIL_DATE) == "2026-07-05"


def test_yearless_date_before_email_rolls_to_next_year():
    # Email sent Dec 2026; "January 5" must mean 2027, not 11 months ago.
    assert normalize_item_date("January 5", "Tue, 15 Dec 2026 09:00:00 -0500") == "2027-01-05"


def test_unparseable_date_is_left_unchanged():
    assert normalize_item_date("sometime soon", EMAIL_DATE) == "sometime soon"


def test_none_date_stays_none():
    assert normalize_item_date(None, EMAIL_DATE) is None


def test_malicious_date_header_never_crashes():
    # The Date header is attacker-controlled (spoofable via SMTP); a huge year
    # makes parsedate_to_datetime raise OverflowError. Must not crash the sync.
    evil = "Wed, 2 Jul 99999999999999999999 10:00:00 -0400"
    assert normalize_item_date("July 5", evil) == "July 5"  # no ref year -> unchanged
    assert normalize_item_date("2026-07-05", evil) == "2026-07-05"


_RFC = "Tue, 01 Jul 2026 09:00:00 -0400"


def test_normalize_strips_bundled_time():
    assert normalize_item_date("July 5th (Saturday) 10:00 AM", _RFC) == "2026-07-05"
    assert normalize_item_date("July 5 at 10am", _RFC) == "2026-07-05"
    assert normalize_item_date("January 5, 2026 3:30pm", _RFC) == "2026-01-05"


def test_normalize_does_not_eat_bare_day():
    # No time token -> the day number must survive.
    assert normalize_item_date("July 5", _RFC) == "2026-07-05"


def test_normalize_iso_and_unparseable_unchanged():
    assert normalize_item_date("2026-07-05", _RFC) == "2026-07-05"
    assert normalize_item_date("sometime next week", _RFC) == "sometime next week"


# --- prompt + wrap carry the date contract ---


def test_wrap_includes_email_date_header():
    wrapped, _ = wrap_untrusted_content("body", "subj", "a@b.org", email_date=EMAIL_DATE)
    assert f"Date: {EMAIL_DATE}" in wrapped


def test_prompt_requires_iso_dates():
    wrapped, nonce = wrap_untrusted_content("body", "subj", "a@b.org", email_date=EMAIL_DATE)
    prompt = build_extraction_prompt(wrapped, nonce)
    assert "YYYY-MM-DD" in prompt


# --- end-to-end through extract_events (mocked client) ---


def test_extract_events_normalizes_prose_dates(monkeypatch):
    block = MagicMock()
    block.type = "tool_use"
    block.input = {"events": [{"item_type": "event", "event_title": "Soccer", "date": "July 5th (Saturday)"}]}
    fake = MagicMock()
    fake.content = [block]
    monkeypatch.setattr(ai_extractor._client.messages, "create", lambda **_: fake)

    out = ai_extractor.extract_events(
        "body", "subj", "coach@club.org", message_id="m1", email_date=EMAIL_DATE
    )

    assert out.events[0].date == "2026-07-05"
