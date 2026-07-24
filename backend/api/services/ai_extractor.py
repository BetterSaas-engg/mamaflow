"""Step 8 — Claude API extraction.

Takes a PII-redacted email, wraps it in nonce-tagged injection
defenses, sends it to Claude, and parses the response into
structured FamilyEvent objects.
"""

import datetime
import email.utils
import logging
import re

import anthropic

from api.config.settings import settings
from api.schemas.family_event import ExtractionResponse
from api.services.content_wrapper import (
    _EXTRACTION_JSON_SCHEMA,
    build_extraction_prompt,
    wrap_untrusted_content,
)

_MAX_TOKENS = 2048  # strict schema emits explicit nulls for every field

# Strict tool use: the tool's schema-locked input IS the extraction result.
# Guarantees valid, schema-conforming output — no JSON-in-text parsing, and
# the locked schema doubles as injection defense (additionalProperties: false).
_EXTRACTION_TOOL = {
    "name": "record_family_items",
    "description": "Record the family events and action items extracted from the email.",
    "strict": True,
    "input_schema": _EXTRACTION_JSON_SCHEMA,
}

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
_log = logging.getLogger(__name__)


_GMAIL_LINK_TEMPLATE = "https://mail.google.com/mail/u/0/#inbox/{message_id}"

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# "July 5th (Saturday)" -> "July 5": drop parentheticals + ordinal suffixes.
_PARENTHETICAL = re.compile(r"\([^)]*\)")
_ORDINAL = re.compile(r"(\d{1,2})(st|nd|rd|th)\b", re.IGNORECASE)
# A trailing clock time bundled into a date string ("July 5 10:00 AM").
# Requires a colon or am/pm so a bare day number is never mistaken for a time.
_TRAILING_TIME = re.compile(
    r"\s+(?:at\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm)\s*$|\s+(?:at\s+)?\d{1,2}:\d{2}\s*$",
    re.IGNORECASE,
)

_DATE_FORMATS_WITH_YEAR = ["%B %d %Y", "%b %d %Y", "%d %B %Y", "%m/%d/%Y", "%m/%d/%y"]
_DATE_FORMATS_YEARLESS = ["%B %d", "%b %d"]


def normalize_item_date(value: str | None, email_date: str = "") -> str | None:
    """Backstop for the prompt's ISO-date rule: coerce common prose dates to
    YYYY-MM-DD so the items date-range filter (ISO string compare) works.

    Yearless dates take their year from the email's Date header; if that puts
    the date more than 30 days before the email was sent, it means the NEXT
    occurrence (a December email about "January 5"). Unparseable values are
    returned unchanged — display still works, only range filtering misses them.
    """
    if value is None:
        return None
    text = value.strip()
    if _ISO_DATE.match(text):
        return text

    cleaned = _PARENTHETICAL.sub("", text)
    cleaned = _ORDINAL.sub(r"\1", cleaned)
    cleaned = cleaned.replace(",", " ")
    cleaned = " ".join(cleaned.split())
    cleaned = _TRAILING_TIME.sub("", cleaned).strip()

    for fmt in _DATE_FORMATS_WITH_YEAR:
        try:
            return datetime.datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue

    ref: datetime.date | None = None
    if email_date:
        try:
            ref = email.utils.parsedate_to_datetime(email_date).date()
        except Exception:
            # The Date header is attacker-controlled (spoofable via SMTP) and
            # parsedate_to_datetime can raise more than ValueError/TypeError —
            # e.g. OverflowError on absurd years. Any failure = no reference.
            ref = None

    if ref is not None:
        for fmt in _DATE_FORMATS_YEARLESS:
            try:
                # Parse with the reference year appended — a bare yearless
                # strptime is deprecated (ambiguous around Feb 29).
                candidate = datetime.datetime.strptime(
                    f"{cleaned} {ref.year}", f"{fmt} %Y"
                ).date()
            except ValueError:
                continue
            if (ref - candidate).days > 30:
                candidate = candidate.replace(year=ref.year + 1)
            return candidate.isoformat()

    # Never log the value itself (audit rule: types only, never values).
    _log.warning("extraction date not normalizable to ISO; left unchanged")
    return value


def extract_events(
    email_body: str,
    email_subject: str,
    sender: str,
    message_id: str = "",
    email_date: str = "",
) -> ExtractionResponse:
    """Run the full extraction pipeline on a single email.

    1. Wrap in nonce-tagged boundaries (injection defense)
    2. Build extraction prompt with locked JSON schema
    3. Call Claude API
    4. Parse JSON response into ExtractionResponse
    5. Normalize dates to ISO + stamp source_email_link (from message_id)
    """
    wrapped, nonce = wrap_untrusted_content(
        email_body, email_subject, sender, email_date=email_date
    )
    prompt = build_extraction_prompt(wrapped, nonce)

    message = _client.messages.create(
        # Settings-driven (D36): Haiku-first for this schema-locked task; the
        # EXTRACTION_MODEL env var flips back to Sonnet without a deploy.
        model=settings.extraction_model,
        max_tokens=_MAX_TOKENS,
        tools=[_EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": _EXTRACTION_TOOL["name"]},
        messages=[{"role": "user", "content": prompt}],
    )

    tool_use = next((b for b in message.content if b.type == "tool_use"), None)
    if tool_use is None:
        # Audit rule: types only, never values — model output is never logged.
        _log.warning("extraction returned no tool_use block; treating as empty")
        return ExtractionResponse(events=[])

    try:
        result = ExtractionResponse.model_validate(tool_use.input)
    except Exception:
        _log.warning("extraction tool input failed schema validation; treating as empty")
        return ExtractionResponse(events=[])

    # Normalize dates to ISO (backstop for the prompt rule) and stamp the
    # Gmail deep link — built server-side, never from Claude output.
    link = _GMAIL_LINK_TEMPLATE.format(message_id=message_id) if message_id else None
    for item in result.events:
        item.date = normalize_item_date(item.date, email_date)
        if link:
            item.source_email_link = link

    return result
