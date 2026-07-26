"""Provider-neutral email body composition helpers (extracted from
gmail_reader for D-multi-provider; used by every mail reader).

Covers the payload-agnostic half of body handling:
  - RFC 5545 (ICS) field extraction → the "Calendar invite details" block (D37)
  - composing the final body text the pipeline treats as the email body

Readers stay responsible for getting raw text out of their own wire format
(Gmail JSON payloads, raw RFC822 over IMAP, Graph JSON later) and hand plain
strings here. Same defensive contract as the readers: malformed input
degrades to "" — one weird email must never fail a sync batch.
"""

import datetime
import re
from zoneinfo import ZoneInfo

from api.config.settings import settings

_ICS_UNESCAPE = {r"\,": ",", r"\;": ";", r"\n": " ", r"\N": " ", "\\\\": "\\"}


def _ics_datetime_to_text(value: str, params: str) -> str:
    """Render an ICS DTSTART/DTEND value as local, human-readable text.

    Handles the three shapes invites actually use: floating/TZID local times
    (used as-is), UTC "Z" times (converted to the app timezone so a 2 PM
    Toronto booking never surfaces as 6 PM), and VALUE=DATE all-day dates.
    Unparseable input returns "" — never raises.
    """
    value = value.strip()
    try:
        if re.fullmatch(r"\d{8}", value):  # all-day: 20260904
            return datetime.datetime.strptime(value, "%Y%m%d").date().isoformat()
        m = re.fullmatch(r"(\d{8})T(\d{6})(Z?)", value)
        if not m:
            return ""
        dt = datetime.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        if m.group(3) == "Z":
            local = dt.replace(tzinfo=datetime.timezone.utc).astimezone(
                ZoneInfo(settings.reminder_tz)
            )
            return local.strftime("%Y-%m-%d %H:%M")
        # TZID/floating: already the organizer's wall-clock time.
        tzid = ""
        tz_match = re.search(r"TZID=([^;:]+)", params)
        if tz_match:
            tzid = f" ({tz_match.group(1)})"
        return dt.strftime("%Y-%m-%d %H:%M") + tzid
    except Exception:
        return ""


def calendar_summary_from_ics(raw: str) -> str:
    """Turn raw ICS text (a text/calendar part) into the plain-text block the
    extractor reads. Returns "" when there is no usable invite."""
    if not raw or "BEGIN:VEVENT" not in raw:
        return ""
    try:
        vevent = raw.split("BEGIN:VEVENT", 1)[1].split("END:VEVENT", 1)[0]
        # RFC 5545 line unfolding: CRLF (or LF) followed by a space/tab
        # continues the previous line.
        vevent = re.sub(r"\r?\n[ \t]", "", vevent)

        fields: dict[str, tuple[str, str]] = {}
        for line in vevent.splitlines():
            if ":" not in line:
                continue
            name_params, value = line.split(":", 1)
            name, _, params = name_params.partition(";")
            name = name.strip().upper()
            if name in ("SUMMARY", "LOCATION", "DTSTART", "DTEND") and name not in fields:
                fields[name] = (value.strip(), params)

        def _text(name: str) -> str:
            value = fields.get(name, ("", ""))[0]
            for esc, plain in _ICS_UNESCAPE.items():
                value = value.replace(esc, plain)
            return value.strip()

        starts = _ics_datetime_to_text(*fields["DTSTART"]) if "DTSTART" in fields else ""
        ends = _ics_datetime_to_text(*fields["DTEND"]) if "DTEND" in fields else ""
        summary = _text("SUMMARY")
        location = _text("LOCATION")
        if not starts and not summary:
            return ""

        lines = ["Calendar invite details (from the attached calendar file):"]
        if summary:
            lines.append(f"Event: {summary}")
        if starts:
            lines.append(f"Starts: {starts}")
        if ends:
            lines.append(f"Ends: {ends}")
        if location:
            lines.append(f"Location: {location}")
        return "\n".join(lines)
    except Exception:
        # Attacker-influenceable input — one weird invite must never fail the
        # sync batch (same contract as the readers' text extraction).
        return ""


def compose_body(text: str, calendar_summary: str) -> str:
    """The text the pipeline treats as the email body: calendar-invite details
    (when present) ahead of the plain-text body. Ordering matters — for
    invites the calendar part holds the real date; the prose often has none
    (D37)."""
    if calendar_summary and text:
        return f"{calendar_summary}\n\n{text}"
    return calendar_summary or text
