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
