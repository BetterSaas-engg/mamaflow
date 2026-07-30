"""Bounded extraction retries (the 2026-07-27 cost bug).

Before this, `mark_message_synced` was written only after SUCCESS and every
failure was swallowed with no counter — so a permanently-failing message was
re-sent to Claude every hour for up to 30 days (~720 full-price calls). That
was ~85% of the observed bill.

Anthropic + Gmail are mocked — never live (testing skill).
"""

import anthropic
import httpx
import pytest

from api.auth.jwt import create_access_token
from api.config.settings import settings as app_settings
from api.schemas.family_event import ExtractionResponse
from api.services import sync_runner
from api.services.ai_extractor import ExtractionUsage
from api.services.users import get_or_create_user
from tests.helpers import user_with_mailbox


def _wire_reader(monkeypatch, metadata):
    """Wire the reader seam: sync lists ids first (cheap), then fetches headers
    only for the unsynced ones. Mirrors the real contract so tests exercise the
    same dedup-before-headers path production uses."""
    by_id = {m["message_id"]: m for m in metadata}
    monkeypatch.setattr(
        sync_runner, "list_recent_ids",
        lambda email, provider="google": list(by_id),
    )
    monkeypatch.setattr(
        sync_runner, "fetch_metadata",
        lambda email, ids, provider="google": [by_id[i] for i in ids if i in by_id],
    )

def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _user_with_token(db, email="parent@example.com"):
    return await user_with_mailbox(db, email)


def _api_error(cls, status):
    """Build a real Anthropic SDK error (they need a request/response)."""
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status, request=request)
    return cls("boom", response=response, body=None)


def _wire(monkeypatch, message_ids, extract_fn):
    metadata = [
        {"message_id": m, "sender": f"{m}@school.org", "subject": "Practice", "date": "Mon"}
        for m in message_ids
    ]
    _wire_reader(monkeypatch, metadata)
    monkeypatch.setattr(
        sync_runner,
        "fetch_message_bodies",
        lambda email, ids, provider="google": {i: "practice on Thursday" for i in ids},
    )
    monkeypatch.setattr(sync_runner, "extract_events", extract_fn)


@pytest.fixture(autouse=True)
def _no_cooldown(monkeypatch):
    monkeypatch.setattr(app_settings, "sync_cooldown_seconds", 0)


async def test_permanent_failure_is_never_retried(client, db, monkeypatch):
    """A 400 means the same input will fail identically forever — one call,
    then never again (this is the 2026-07-15 invalid-schema class)."""
    _, token = await _user_with_token(db)
    calls = []

    def fake_extract(body, subject, sender, message_id="", email_date="", provider="google"):
        calls.append(message_id)
        raise _api_error(anthropic.BadRequestError, 400)

    _wire(monkeypatch, ["m1"], fake_extract)

    await client.post("/api/v1/sync", headers=_auth(token))
    await client.post("/api/v1/sync", headers=_auth(token))
    await client.post("/api/v1/sync", headers=_auth(token))

    assert calls == ["m1"]  # ONE call ever, not one per sync


async def test_transient_failure_retries_then_gives_up(client, db, monkeypatch):
    """A rate limit deserves retries — but a bounded number of them."""
    _, token = await _user_with_token(db)
    monkeypatch.setattr(app_settings, "extraction_max_attempts", 3)
    calls = []

    def fake_extract(body, subject, sender, message_id="", email_date="", provider="google"):
        calls.append(message_id)
        raise _api_error(anthropic.RateLimitError, 429)

    _wire(monkeypatch, ["m1"], fake_extract)

    for _ in range(6):  # six syncs, only three may reach Claude
        await client.post("/api/v1/sync", headers=_auth(token))

    assert len(calls) == 3


async def test_success_after_a_transient_failure_clears_the_failure_state(
    client, db, monkeypatch
):
    """Success is terminal — a message that failed once then succeeded must not
    carry a failure marker that could later be mistaken for a give-up."""
    _, token = await _user_with_token(db)
    calls = []

    def fake_extract(body, subject, sender, message_id="", email_date="", provider="google"):
        calls.append(message_id)
        if len(calls) == 1:
            raise _api_error(anthropic.InternalServerError, 500)
        return ExtractionResponse(events=[]), ExtractionUsage(input_tokens=1, output_tokens=1)

    _wire(monkeypatch, ["m1"], fake_extract)

    await client.post("/api/v1/sync", headers=_auth(token))  # fails
    await client.post("/api/v1/sync", headers=_auth(token))  # succeeds
    await client.post("/api/v1/sync", headers=_auth(token))  # skipped

    assert len(calls) == 2

    from api.services.items import existing_message_ids

    assert await existing_message_ids(db, (await _user_with_token(db))[0].id, ["m1"]) == {"m1"}


async def test_auth_error_aborts_the_run_without_burning_the_batch(
    client, db, monkeypatch
):
    """A bad API key is account-level. Retrying each message would burn the
    whole batch into a wall, so the run fails after the first call."""
    _, token = await _user_with_token(db)
    calls = []

    def fake_extract(body, subject, sender, message_id="", email_date="", provider="google"):
        calls.append(message_id)
        raise _api_error(anthropic.AuthenticationError, 401)

    _wire(monkeypatch, ["m1", "m2", "m3", "m4", "m5"], fake_extract)

    await client.post("/api/v1/sync", headers=_auth(token))
    status = (await client.get("/api/v1/sync/status", headers=_auth(token))).json()

    assert len(calls) == 1  # not 5
    assert status["status"] == "failed"


async def test_circuit_breaker_caps_a_provider_outage(client, db, monkeypatch):
    """An outage would otherwise cost a full batch of failed calls per user,
    every hourly tick."""
    _, token = await _user_with_token(db)
    monkeypatch.setattr(app_settings, "extraction_failure_breaker", 5)
    calls = []

    def fake_extract(body, subject, sender, message_id="", email_date="", provider="google"):
        calls.append(message_id)
        raise _api_error(anthropic.InternalServerError, 500)

    _wire(monkeypatch, [f"m{i}" for i in range(10)], fake_extract)

    await client.post("/api/v1/sync", headers=_auth(token))

    assert len(calls) == 5  # breaker tripped, not all 10


async def test_daily_budget_caps_runaway_spend(client, db, monkeypatch):
    """The backstop against the NEXT runaway, whatever it turns out to be."""
    _, token = await _user_with_token(db)
    monkeypatch.setattr(app_settings, "extraction_daily_call_budget", 3)
    calls = []

    def fake_extract(body, subject, sender, message_id="", email_date="", provider="google"):
        calls.append(message_id)
        return ExtractionResponse(events=[]), ExtractionUsage(input_tokens=10, output_tokens=2)

    _wire(monkeypatch, [f"m{i}" for i in range(8)], fake_extract)

    await client.post("/api/v1/sync", headers=_auth(token))

    assert len(calls) == 3  # budget stops the run mid-batch


# --- Audit follow-ups (2026-07-27 security review) ---


async def test_early_abort_does_not_report_full_completion(client, db, monkeypatch):
    """An abort leaves the remainder untried; telling the client 'processed:
    all of them' would be a lie (they are retried next sync)."""
    _, token = await _user_with_token(db)
    monkeypatch.setattr(app_settings, "extraction_daily_call_budget", 2)

    def fake_extract(body, subject, sender, message_id="", email_date="", provider="google"):
        return ExtractionResponse(events=[]), ExtractionUsage(input_tokens=5, output_tokens=1)

    _wire(monkeypatch, [f"m{i}" for i in range(6)], fake_extract)

    await client.post("/api/v1/sync", headers=_auth(token))
    status = (await client.get("/api/v1/sync/status", headers=_auth(token))).json()

    # Only the 2 that fit the budget were attempted — previously this reported
    # 6, claiming work that never happened. (finish() mirrors to_process to
    # processed; the untried 4 are simply picked up by the next sync.)
    assert status["processed"] == 2


async def test_reset_reopens_given_up_messages_but_not_successes(client, db, monkeypatch):
    """Recovery path for a SYSTEMIC fault misclassified as permanent — without
    it, a bad deploy would blacklist every message it touched, forever."""
    from api.db import reset_failed_messages as reset_mod
    from api.services.items import existing_message_ids, mark_message_synced, record_message_failure

    user, _ = await _user_with_token(db)
    await mark_message_synced(db, user.id, "ok1")                     # success
    await record_message_failure(db, user.id, "bad1", "permanent")    # give-up

    assert await existing_message_ids(db, user.id, ["ok1", "bad1"]) == {"ok1", "bad1"}

    # The script opens its own session; point it at the test session factory.
    monkeypatch.setattr(reset_mod, "AsyncSessionLocal", lambda: _Ctx(db))
    cleared = await reset_mod.reset_failed_messages(kind="permanent")

    assert cleared == 1
    # The give-up is eligible again; the success is untouched (never re-billed).
    assert await existing_message_ids(db, user.id, ["ok1", "bad1"]) == {"ok1"}


class _Ctx:
    """Async-context wrapper so the script can use the test's session."""

    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *exc):
        return False
