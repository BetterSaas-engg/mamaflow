import base64
import datetime
import re
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from api.auth.token_store import get_token
from api.config.settings import settings
from api.services.google_token import ensure_fresh

MAX_PREVIEW_MESSAGES = 50


def _build_gmail_client(user_email: str):
    token_data = get_token(user_email)
    if not token_data:
        raise ValueError(f"No stored token for {user_email}")

    # Mobile PKCE credentials (client_secret is None) can't be refreshed by
    # google-auth; refresh + re-store them here before building the client.
    token_data = ensure_fresh(user_email, token_data)

    creds = Credentials(
        token=token_data["token"],
        refresh_token=token_data["refresh_token"],
        token_uri=token_data["token_uri"],
        client_id=token_data["client_id"],
        client_secret=token_data["client_secret"],
        scopes=token_data["scopes"],
    )
    return build("gmail", "v1", credentials=creds)


def _extract_header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower() and "value" in h:
            return h["value"]
    return ""


def _extract_plain_text(payload: dict) -> str:
    """Walk MIME parts to find text/plain and base64url-decode it.

    The payload is attacker-influenceable (anyone can email the user), so a
    malformed part degrades to "" — one bad message must never raise and fail
    the whole sync batch.
    """
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            try:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            except (ValueError, TypeError):  # binascii.Error is a ValueError
                return ""
        return ""

    # Recurse into multipart
    for part in payload.get("parts", []):
        text = _extract_plain_text(part)
        if text:
            return text

    return ""


# --- Calendar-invite parsing (D37) -----------------------------------------
# Bookings/Teams/Google invites carry the actual event data (DTSTART/SUMMARY/
# LOCATION) in a text/calendar MIME part; the body text usually has NO meeting
# date at all, so without this the extractor cannot see the event. Minimal
# RFC 5545 field extraction — not a full parser; anything unexpected → "".

_ICS_UNESCAPE = {r"\,": ",", r"\;": ";", r"\n": " ", r"\N": " ", "\\\\": "\\"}


def _extract_calendar_raw(payload: dict) -> str:
    """Find the first text/calendar part and decode it. Same defensive
    contract as _extract_plain_text: malformed input degrades to ""."""
    if payload.get("mimeType", "") == "text/calendar":
        data = payload.get("body", {}).get("data", "")
        if data:
            try:
                return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            except (ValueError, TypeError):
                return ""
        return ""
    for part in payload.get("parts", []):
        raw = _extract_calendar_raw(part)
        if raw:
            return raw
    return ""


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


def _extract_calendar_summary(payload: dict) -> str:
    """Turn the message's text/calendar part (if any) into a plain-text block
    the extractor can read. Returns "" when there is no usable invite."""
    raw = _extract_calendar_raw(payload)
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
        # sync batch (same contract as _extract_plain_text).
        return ""


def _compose_body(payload: dict) -> str:
    """The text the pipeline treats as the email body: calendar-invite details
    (when present) ahead of the plain-text body. Ordering matters — for
    invites the calendar part holds the real date; the prose often has none."""
    text = _extract_plain_text(payload)
    calendar = _extract_calendar_summary(payload)
    if calendar and text:
        return f"{calendar}\n\n{text}"
    return calendar or text


def _list_recent_ids(gmail) -> list[str]:
    thirty_days_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    query = f"after:{int(thirty_days_ago.timestamp())}"

    results = gmail.users().messages().list(
        userId="me",
        q=query,
        maxResults=MAX_PREVIEW_MESSAGES,
    ).execute()

    return [m["id"] for m in results.get("messages", [])]


def fetch_recent_metadata(user_email: str) -> list[dict]:
    """List the last 30 days of messages with HEADERS ONLY (format="metadata").

    No body is fetched here. The caller checks each sender against the blocklist
    and fetches the body ONLY for senders that pass (AGENTS.md: metadata-first;
    a blocked sender's body is never pulled).
    """
    gmail = _build_gmail_client(user_email)
    metadata = []
    for message_id in _list_recent_ids(gmail):
        msg = gmail.users().messages().get(
            userId="me",
            id=message_id,
            format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        ).execute()
        headers = msg.get("payload", {}).get("headers", [])
        metadata.append({
            "message_id": msg["id"],
            "sender": _extract_header(headers, "From"),
            "subject": _extract_header(headers, "Subject"),
            "date": _extract_header(headers, "Date"),
        })
    return metadata


def fetch_message_bodies(user_email: str, message_ids: list[str]) -> dict[str, str]:
    """Fetch full bodies for the given message ids (format="full").

    Only call this with ids whose senders have already passed the blocklist.
    """
    if not message_ids:
        return {}

    gmail = _build_gmail_client(user_email)
    bodies = {}
    for message_id in message_ids:
        msg = gmail.users().messages().get(
            userId="me",
            id=message_id,
            format="full",
        ).execute()
        bodies[message_id] = _compose_body(msg.get("payload", {}))
    return bodies
