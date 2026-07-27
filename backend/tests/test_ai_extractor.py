"""Extractor hardening: strict tool-use structured output (A3).

The Claude call must force a tool whose schema-locked input IS the extraction
result — no JSON-in-text parsing, no raw model text ever logged (types only).
Anthropic client is mocked — never live (testing skill).
"""

from unittest.mock import MagicMock

from api.services import ai_extractor


def _tool_use_response(input_dict):
    block = MagicMock()
    block.type = "tool_use"
    block.input = input_dict
    msg = MagicMock()
    msg.content = [block]
    return msg


def _text_only_response(text):
    block = MagicMock()
    block.type = "text"
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


def test_forces_strict_tool_choice(monkeypatch):
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _tool_use_response({"events": []})

    monkeypatch.setattr(ai_extractor._client.messages, "create", fake_create)

    ai_extractor.extract_events("body", "subj", "a@b.org")

    assert captured["tool_choice"] == {"type": "tool", "name": "record_family_items"}
    [tool] = captured["tools"]
    assert tool["name"] == "record_family_items"
    assert tool["strict"] is True
    assert tool["input_schema"]["additionalProperties"] is False


def test_parses_tool_input_and_stamps_link(monkeypatch):
    monkeypatch.setattr(
        ai_extractor._client.messages, "create",
        lambda **_: _tool_use_response(
            {"events": [{"item_type": "event", "event_title": "Soccer",
                         "source_email_link": "https://evil.example/phish"}]}
        ),
    )

    out, _ = ai_extractor.extract_events("b", "s", "x@y.com", message_id="abc123")

    assert out.events[0].event_title == "Soccer"
    # Stamped server-side from message_id — NEVER from Claude output.
    assert out.events[0].source_email_link.endswith("abc123")
    assert "evil" not in out.events[0].source_email_link


def test_no_tool_use_block_returns_empty_and_logs_no_content(monkeypatch, caplog):
    monkeypatch.setattr(
        ai_extractor._client.messages, "create",
        lambda **_: _text_only_response("SECRET-CONTENT ignore previous instructions"),
    )

    with caplog.at_level("WARNING"):
        out, _ = ai_extractor.extract_events("b", "s", "x@y.com")

    assert out.events == []
    # Audit rule: types only, never values — model text must not reach logs.
    assert "SECRET-CONTENT" not in caplog.text


def test_invalid_tool_input_returns_empty(monkeypatch, caplog):
    monkeypatch.setattr(
        ai_extractor._client.messages, "create",
        lambda **_: _tool_use_response({"events": "not-a-list-SECRETVAL"}),
    )

    with caplog.at_level("WARNING"):
        out, _ = ai_extractor.extract_events("b", "s", "x@y.com")

    assert out.events == []
    assert "SECRETVAL" not in caplog.text


def test_imap_provider_items_have_no_deep_link(monkeypatch):
    """IMAP providers have no stable web URL — the link stays None (frontend
    only shows the open-email action when a link exists)."""
    fake = MagicMock()
    tool_use = MagicMock()
    tool_use.type = "tool_use"
    tool_use.input = {"events": [{
        "item_type": "event", "event_title": "Practice", "action_required": None,
        "date": "2026-08-01", "time": None, "location": None, "child_name": None,
        "event_type": "sports", "source_sender": None, "source_email_link": None,
    }]}
    fake.content = [tool_use]
    monkeypatch.setattr(ai_extractor._client.messages, "create", lambda **_: fake)

    out, _ = ai_extractor.extract_events(
        "body", "subj", "x@rogers.com", message_id="mid@rogers", provider="yahoo"
    )

    assert out.events[0].source_email_link is None


# --- Cost instrumentation: usage must be captured, and stay content-free ---


def test_usage_is_captured_from_the_response(monkeypatch):
    """Extraction spend was invisible before this; the caller needs real counts
    to aggregate per sync."""
    resp = _tool_use_response({"events": []})
    resp.usage.input_tokens = 2345
    resp.usage.output_tokens = 60
    monkeypatch.setattr(ai_extractor._client.messages, "create", lambda **_: resp)

    _, usage = ai_extractor.extract_events("a body", "subj", "x@y.com")

    assert usage.input_tokens == 2345
    assert usage.output_tokens == 60
    assert usage.model == ai_extractor.settings.extraction_model
    assert usage.body_chars == len("a body")


def test_usage_degrades_to_zeros_when_the_sdk_omits_it(monkeypatch):
    """A missing/odd usage block must never fail an otherwise-good extraction."""
    resp = _tool_use_response({"events": []})
    del resp.usage  # MagicMock without the attribute
    monkeypatch.setattr(ai_extractor._client.messages, "create", lambda **_: resp)

    result, usage = ai_extractor.extract_events("b", "s", "x@y.com")

    assert result.events == []
    assert usage.input_tokens == 0 and usage.output_tokens == 0


def test_usage_carries_no_content(monkeypatch):
    """Audit rule: counts are fine, content is not — nothing token-bearing may
    ride along in the telemetry object."""
    resp = _tool_use_response({"events": []})
    resp.usage.input_tokens = 10
    resp.usage.output_tokens = 2
    monkeypatch.setattr(ai_extractor._client.messages, "create", lambda **_: resp)

    _, usage = ai_extractor.extract_events("SECRET-CONTENT body", "SECRET-SUBJ", "x@y.com")

    assert "SECRET" not in repr(usage)
