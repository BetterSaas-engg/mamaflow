---
name: testing
description: Use when writing or running tests for the Mamaflow backend (pytest in backend/tests) — conventions, what to cover per pipeline layer, and mocking the Anthropic/Gmail clients so tests never hit live APIs.
---

# Testing (Mamaflow backend)

Run from `backend/` so the `api` package imports: `cd backend && python -m pytest`. Tests live in
`backend/tests/`. For the RED→GREEN discipline, use `superpowers:test-driven-development`; this skill
is the Mamaflow-specific *what* and *how*.

## Cover per pipeline layer

- **Sender filter** (`sender_blocklist.py`): allowlist beats blocklist; exact-domain block; regex
  block; unknown passes through; soft-deleted rows ignored.
- **PII redaction** (`privacy_pipeline.py`): each entity redacted (credit card, US bank, IBAN, US
  SSN, Canadian SIN, generic account number); contextual PII (phone, DOB, names, addresses) preserved.
- **Injection wrap** (`content_wrapper.py`): nonce is randomized; "ignore previous instructions" in
  the body stays inert. (See existing `test_content_wrapper.py` — the model to follow.)
- **Extractor** (`ai_extractor.py`): valid JSON → populated `FamilyItem`s; garbage/non-JSON →
  `ExtractionResponse(events=[])`; `source_email_link` stamped from `message_id`, never from output.

## Never call live APIs

Mock the Anthropic and Gmail clients. The extractor holds a module-level `_client`:

```python
# backend/tests/test_ai_extractor.py
from unittest.mock import MagicMock
from api.services import ai_extractor

def test_parses_and_stamps_link(monkeypatch):
    fake = MagicMock()
    fake.content = [MagicMock(text='{"events":[{"item_type":"event","event_title":"Soccer"}]}')]
    monkeypatch.setattr(ai_extractor._client.messages, "create", lambda **_: fake)
    out = ai_extractor.extract_events("body", "subj", "from@school.org", message_id="abc123")
    assert out.events[0].event_title == "Soccer"
    assert out.events[0].source_email_link.endswith("abc123")

def test_bad_json_returns_empty(monkeypatch):
    fake = MagicMock(); fake.content = [MagicMock(text="not json")]
    monkeypatch.setattr(ai_extractor._client.messages, "create", lambda **_: fake)
    assert ai_extractor.extract_events("b", "s", "x@y.com").events == []
```

## Conventions

- Async DB code: `pytest.mark.asyncio` (or `anyio`); use a test session, never the dev DB.
- Mock at the boundary (the client), not the parsing logic — assert on real `FamilyItem` output.
- No secrets in tests; no real `.env`.
