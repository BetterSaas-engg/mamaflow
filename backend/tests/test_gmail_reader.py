"""Unit tests for gmail_reader's pure parsing helpers (no Gmail client).

The MIME/base64 payload is attacker-influenceable (anyone can email the user),
so malformed input must degrade to "" per message — never an exception that
fails a whole sync batch.
"""

import base64

from api.services.gmail_reader import _extract_header, _extract_plain_text


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def test_extract_plain_text_decodes_simple_body():
    payload = {"mimeType": "text/plain", "body": {"data": _b64("hello")}}
    assert _extract_plain_text(payload) == "hello"


def test_extract_plain_text_malformed_base64_returns_empty():
    # "ab" is invalid base64url padding -> binascii.Error if unhandled.
    payload = {"mimeType": "text/plain", "body": {"data": "ab"}}
    assert _extract_plain_text(payload) == ""


def test_extract_plain_text_walks_multipart_for_plain_part():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<b>hi</b>")}},
            {"mimeType": "text/plain", "body": {"data": _b64("hi")}},
        ],
    }
    assert _extract_plain_text(payload) == "hi"


def test_extract_plain_text_corrupt_part_falls_through_to_next():
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": "!!not-base64!!"}},
            {"mimeType": "text/plain", "body": {"data": _b64("good part")}},
        ],
    }
    assert _extract_plain_text(payload) == "good part"


def test_extract_plain_text_no_plain_part_returns_empty():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [{"mimeType": "text/html", "body": {"data": _b64("<b>x</b>")}}],
    }
    assert _extract_plain_text(payload) == ""


def test_extract_plain_text_invalid_utf8_is_replaced_not_raised():
    data = base64.urlsafe_b64encode(b"\xff\xfe bad bytes").decode()
    payload = {"mimeType": "text/plain", "body": {"data": data}}
    out = _extract_plain_text(payload)
    assert "bad bytes" in out  # decoded with replacement, not raised


def test_extract_header_is_case_insensitive():
    headers = [{"name": "FROM", "value": "a@b.c"}]
    assert _extract_header(headers, "from") == "a@b.c"


def test_extract_header_missing_returns_empty():
    assert _extract_header([{"name": "Subject", "value": "s"}], "From") == ""


def test_extract_header_malformed_entries_are_skipped():
    headers = [{}, {"name": "From"}, {"value": "x"}, {"name": "From", "value": "ok@x.c"}]
    assert _extract_header(headers, "From") == "ok@x.c"


def test_build_gmail_client_refreshes_mobile_token(monkeypatch):
    """The Gmail client must be built from a fresh token: _build_gmail_client
    routes the stored credential through google_token.ensure_fresh (which
    refreshes an expired mobile PKCE credential) before constructing creds."""
    from api.services import gmail_reader

    stored = {
        "token": "FAKE-STALE", "refresh_token": "FAKE-R",
        "token_uri": "https://oauth2.googleapis.com/token",
        "client_id": "ios", "client_secret": None, "scopes": ["s"],
    }
    monkeypatch.setattr(gmail_reader, "get_token", lambda email: dict(stored))
    monkeypatch.setattr(
        gmail_reader, "ensure_fresh",
        lambda email, td: {**td, "token": "FAKE-FRESH"},
    )
    captured = {}
    monkeypatch.setattr(
        gmail_reader, "Credentials",
        lambda **kw: captured.update(kw) or object(),
    )
    monkeypatch.setattr(gmail_reader, "build", lambda *a, **k: "gmail-client")

    client = gmail_reader._build_gmail_client("p@x.com")

    assert client == "gmail-client"
    assert captured["token"] == "FAKE-FRESH"  # the REFRESHED token, not the stale one


# --- Calendar-invite parsing (D37): event data lives in text/calendar, ---
# --- not the body text; the reader must surface it for extraction.     ---

from api.services.gmail_reader import _compose_body, _extract_calendar_summary  # noqa: E402

_ICS_TORONTO = (
    "BEGIN:VCALENDAR\r\n"
    "BEGIN:VEVENT\r\n"
    "SUMMARY:Akhil Kaushal - 25 Minute Discovery Session\r\n"
    "DTSTART;TZID=America/Toronto:20260806T140000\r\n"
    "DTEND;TZID=America/Toronto:20260806T142500\r\n"
    "LOCATION:Microsoft Teams meeting\r\n"
    "END:VEVENT\r\n"
    "END:VCALENDAR\r\n"
)


def _cal_payload(ics: str) -> dict:
    return {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": _b64("<p>hi</p>")}},
            {"mimeType": "text/calendar", "body": {"data": _b64(ics)}},
        ],
    }


def test_calendar_summary_extracts_event_fields():
    out = _extract_calendar_summary(_cal_payload(_ICS_TORONTO))
    assert "Akhil Kaushal - 25 Minute Discovery Session" in out
    assert "2026-08-06" in out
    assert "14:00" in out
    assert "Microsoft Teams meeting" in out


def test_calendar_summary_converts_utc_to_local():
    # 18:00Z on Aug 6 is 14:00 in America/Toronto (EDT) — the invite must not
    # surface as a 6 PM meeting when the user booked 2 PM local.
    ics = (
        "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n"
        "SUMMARY:Checkup\r\n"
        "DTSTART:20260806T180000Z\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    out = _extract_calendar_summary(_cal_payload(ics))
    assert "2026-08-06" in out
    assert "14:00" in out


def test_calendar_summary_all_day_event_has_date_only():
    ics = (
        "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n"
        "SUMMARY:PA Day\r\n"
        "DTSTART;VALUE=DATE:20260904\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    out = _extract_calendar_summary(_cal_payload(ics))
    assert "PA Day" in out
    assert "2026-09-04" in out


def test_calendar_summary_unfolds_wrapped_lines_and_unescapes():
    # RFC 5545: long lines fold with CRLF + one space; unfolding strips BOTH,
    # so a mid-word fold ("Conf" / "erence") must rejoin without a gap.
    # Commas escape as backslash-comma.
    ics = (
        "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n"
        "SUMMARY:Parent Teacher Conf\r\n erence\r\n"
        "DTSTART;VALUE=DATE:20260910\r\n"
        "LOCATION:Room 12\\, Riverside Elementary\r\n"
        "END:VEVENT\r\nEND:VCALENDAR\r\n"
    )
    out = _extract_calendar_summary(_cal_payload(ics))
    assert "Parent Teacher Conference" in out
    assert "Room 12, Riverside Elementary" in out


def test_calendar_summary_no_calendar_part_is_empty():
    payload = {"mimeType": "text/plain", "body": {"data": _b64("hello")}}
    assert _extract_calendar_summary(payload) == ""


def test_calendar_summary_garbage_never_raises():
    assert _extract_calendar_summary(_cal_payload("not ics at all")) == ""
    bad = {
        "mimeType": "multipart/mixed",
        "parts": [{"mimeType": "text/calendar", "body": {"data": "ab"}}],
    }
    assert _extract_calendar_summary(bad) == ""


def test_compose_body_prepends_calendar_summary_to_plain_text():
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": _b64("See you there!")}},
            {"mimeType": "text/calendar", "body": {"data": _b64(_ICS_TORONTO)}},
        ],
    }
    out = _compose_body(payload)
    assert "2026-08-06" in out
    assert "See you there!" in out
    assert out.index("2026-08-06") < out.index("See you there!")


def test_compose_body_calendar_only_still_yields_text():
    # Invites with no text/plain part must not come back empty (the gate would
    # skip them on subject alone — the original 2026-07-24 bug shape).
    out = _compose_body(_cal_payload(_ICS_TORONTO))
    assert "2026-08-06" in out


# --- Pagination (the mechanism that fixes the silent-drop bug) ---
#
# The sync-level tests use fakes that bypass this loop entirely, so the loop
# itself was untested — exactly the code whose absence caused the bug.


class _FakeMessages:
    """Records list() calls and serves ids in 100-id pages, like Gmail."""

    def __init__(self, ids):
        self._ids = ids
        self.calls = []

    def list(self, userId, q, maxResults, pageToken=None):
        self.calls.append({"maxResults": maxResults, "pageToken": pageToken})
        start = int(pageToken or 0)
        page = self._ids[start : start + maxResults]
        nxt = start + len(page)
        return _FakeExec(
            {
                "messages": [{"id": i} for i in page],
                **({"nextPageToken": str(nxt)} if nxt < len(self._ids) else {}),
            }
        )


class _FakeExec:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


class _FakeUsers:
    def __init__(self, messages):
        self._messages = messages

    def messages(self):
        return self._messages


class _FakeGmail:
    def __init__(self, messages):
        self._users = _FakeUsers(messages)

    def users(self):
        return self._users


def _wire_gmail(monkeypatch, ids):
    from api.services import gmail_reader

    messages = _FakeMessages(ids)
    monkeypatch.setattr(
        gmail_reader, "_build_gmail_client", lambda email: _FakeGmail(messages)
    )
    return messages


def test_list_recent_ids_pages_past_the_first_100(monkeypatch):
    """The original bug: one un-paginated page meant everything older was
    never listed again, so it could never be extracted."""
    from api.config.settings import settings as app_settings
    from api.services import gmail_reader

    monkeypatch.setattr(app_settings, "sync_scan_max_messages", 500)
    messages = _wire_gmail(monkeypatch, [f"m{i:03d}" for i in range(250)])

    ids = gmail_reader.list_recent_ids("parent@example.com")

    assert len(ids) == 250  # not 100 — it followed nextPageToken
    assert ids[0] == "m000" and ids[-1] == "m249"
    assert [c["pageToken"] for c in messages.calls] == [None, "100", "200"]


def test_list_recent_ids_stops_at_the_scan_cap(monkeypatch):
    """Wide, but still bounded — the cap is what keeps a huge mailbox from
    turning one sync into an unbounded crawl."""
    from api.config.settings import settings as app_settings
    from api.services import gmail_reader

    monkeypatch.setattr(app_settings, "sync_scan_max_messages", 150)
    messages = _wire_gmail(monkeypatch, [f"m{i:03d}" for i in range(400)])

    ids = gmail_reader.list_recent_ids("parent@example.com")

    assert len(ids) == 150
    # Second page asks for exactly the remainder, never a wasted full page.
    assert [c["maxResults"] for c in messages.calls] == [100, 50]


def test_list_recent_ids_handles_an_empty_mailbox(monkeypatch):
    from api.services import gmail_reader

    _wire_gmail(monkeypatch, [])

    assert gmail_reader.list_recent_ids("parent@example.com") == []
