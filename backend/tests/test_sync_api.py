"""Tests for background + incremental sync (A2).

Contract:
  POST /api/v1/sync         -> 202 {"status": "started"}  (extraction runs as a
                               background task; with ASGITransport background
                               tasks finish before the response reaches us, so
                               status is terminal right after the POST)
  GET  /api/v1/sync/status  -> per-user {"status": idle|running|done|failed, counts}

Gmail + Claude are mocked — never live. Load-bearing invariants:
  - a blocked sender's body is never fetched (metadata-first)
  - already-synced messages are skipped BEFORE body fetch/extraction (no
    repeat Claude spend)
"""

from api.auth.jwt import create_access_token
from api.models.sender_blocklist import SenderBlocklist
from api.schemas.family_event import ExtractionResponse, FamilyItem
from api.services import sync_runner
from api.services.users import get_or_create_user


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _user_with_token(db, email="parent@example.com"):
    user = await get_or_create_user(db, email)
    return user, create_access_token(subject=str(user.id), email=user.email)


async def test_sync_requires_auth(client):
    assert (await client.post("/api/v1/sync")).status_code == 401
    assert (await client.get("/api/v1/sync/status")).status_code == 401


async def test_debug_preview_endpoints_are_removed(client):
    """Phase-0 debug GETs (unused by the app) had no cooldown and returned
    redacted body text — removed rather than hardened (2026-07-10 audit)."""
    assert (await client.get("/api/v1/sync/preview")).status_code == 404
    assert (await client.get("/api/v1/sync/preview-filtered")).status_code == 404
    assert (await client.get("/api/v1/sync/extract")).status_code == 404


async def test_status_is_idle_before_any_sync(client, db):
    _, token = await _user_with_token(db)

    resp = await client.get("/api/v1/sync/status", headers=_auth(token))

    assert resp.status_code == 200
    assert resp.json()["status"] == "idle"


async def test_sync_runs_in_background_and_reports_done(client, db, monkeypatch):
    user, token = await _user_with_token(db)
    db.add(SenderBlocklist(domain="blocked.com", category="financial", reason="test"))
    await db.commit()

    metadata = [
        {"message_id": "m_ok", "sender": "school@allowed.org", "subject": "Soccer", "date": "Mon"},
        {"message_id": "m_block", "sender": "billing@blocked.com", "subject": "Invoice", "date": "Tue"},
    ]
    monkeypatch.setattr(sync_runner, "fetch_recent_metadata", lambda email: metadata)

    fetched_ids = []

    def fake_bodies(email, ids):
        fetched_ids.extend(ids)
        return {mid: "practice on Thursday" for mid in ids}

    monkeypatch.setattr(sync_runner, "fetch_message_bodies", fake_bodies)
    monkeypatch.setattr(
        sync_runner, "extract_events",
        lambda body, subject, sender, message_id="", email_date="": ExtractionResponse(
            events=[FamilyItem(item_type="event", event_title="Soccer", date="2026-06-20")]
        ),
    )

    resp = await client.post("/api/v1/sync", headers=_auth(token))

    assert resp.status_code == 202
    assert resp.json()["status"] == "started"

    status = (await client.get("/api/v1/sync/status", headers=_auth(token))).json()
    assert status["status"] == "done"
    assert status["messages_scanned"] == 2
    assert status["blocked"] == 1
    assert status["items_created"] == 1

    # Metadata-first invariant: the blocked sender's body was never fetched.
    assert fetched_ids == ["m_ok"]

    listed = await client.get("/api/v1/items", headers=_auth(token))
    assert len(listed.json()["items"]) == 1


async def test_resync_skips_already_synced_before_extraction(client, db, monkeypatch):
    """Incremental: the second sync must not re-fetch bodies or re-extract
    messages that are already persisted — dedup happens BEFORE Claude."""
    from api.config.settings import settings as app_settings

    monkeypatch.setattr(app_settings, "sync_cooldown_seconds", 0)
    user, token = await _user_with_token(db)
    metadata = [{"message_id": "m1", "sender": "a@x.org", "subject": "S", "date": "Mon"}]
    monkeypatch.setattr(sync_runner, "fetch_recent_metadata", lambda email: metadata)

    body_calls = []
    extract_calls = []

    def fake_bodies(email, ids):
        body_calls.append(list(ids))
        return {i: "practice on Thursday" for i in ids}

    def fake_extract(body, subject, sender, message_id="", email_date=""):
        extract_calls.append(message_id)
        return ExtractionResponse(events=[FamilyItem(item_type="event", event_title="X")])

    monkeypatch.setattr(sync_runner, "fetch_message_bodies", fake_bodies)
    monkeypatch.setattr(sync_runner, "extract_events", fake_extract)

    await client.post("/api/v1/sync", headers=_auth(token))
    first = (await client.get("/api/v1/sync/status", headers=_auth(token))).json()
    await client.post("/api/v1/sync", headers=_auth(token))
    second = (await client.get("/api/v1/sync/status", headers=_auth(token))).json()

    assert first["items_created"] == 1
    assert second["items_created"] == 0
    assert extract_calls == ["m1"]  # extraction ran ONCE, not twice
    assert body_calls == [["m1"], []] or body_calls == [["m1"]]  # no re-fetch

    listed = await client.get("/api/v1/items", headers=_auth(token))
    assert len(listed.json()["items"]) == 1


async def test_resync_skips_zero_event_messages(client, db, monkeypatch):
    """The 2026-07-23 cost bug: an email that extracted NO events left no items
    row, so dedup never recognized it and every sync re-sent it to Claude
    (hourly auto-sync × the whole 30-day window ≈ $10 CAD/day). The
    synced_messages marker must make the second sync skip it entirely."""
    from api.config.settings import settings as app_settings

    monkeypatch.setattr(app_settings, "sync_cooldown_seconds", 0)
    user, token = await _user_with_token(db)
    metadata = [{"message_id": "m1", "sender": "a@x.org", "subject": "S", "date": "Mon"}]
    monkeypatch.setattr(sync_runner, "fetch_recent_metadata", lambda email: metadata)

    extract_calls = []

    def fake_extract(body, subject, sender, message_id="", email_date=""):
        extract_calls.append(message_id)
        return ExtractionResponse(events=[])  # newsletter: nothing extractable

    monkeypatch.setattr(sync_runner, "fetch_message_bodies", lambda email, ids: {i: "practice on Thursday" for i in ids})
    monkeypatch.setattr(sync_runner, "extract_events", fake_extract)

    await client.post("/api/v1/sync", headers=_auth(token))
    await client.post("/api/v1/sync", headers=_auth(token))
    second = (await client.get("/api/v1/sync/status", headers=_auth(token))).json()

    assert extract_calls == ["m1"]  # Claude called ONCE ever, despite zero items
    assert second["to_process"] == 0  # second sync had nothing to do


async def test_gated_email_never_reaches_claude_and_stays_skipped(client, db, monkeypatch):
    """D36 gate: an email with no temporal/family signal skips Presidio AND
    Claude, is still marked synced (no re-check next sync), and counts as
    processed in the status counters."""
    from api.config.settings import settings as app_settings

    monkeypatch.setattr(app_settings, "sync_cooldown_seconds", 0)
    user, token = await _user_with_token(db)
    metadata = [
        {"message_id": "m_gate", "sender": "shop@store.com", "subject": "Update", "date": "Mon"},
        {"message_id": "m_real", "sender": "school@x.org", "subject": "Practice", "date": "Mon"},
    ]
    monkeypatch.setattr(sync_runner, "fetch_recent_metadata", lambda email: metadata)
    bodies = {
        "m_gate": "Discover our newest arrivals with free shipping.",  # no signal
        "m_real": "Soccer practice moves to Thursday 3:30 PM.",
    }
    monkeypatch.setattr(sync_runner, "fetch_message_bodies", lambda email, ids: bodies)

    extract_calls = []

    def fake_extract(body, subject, sender, message_id="", email_date=""):
        extract_calls.append(message_id)
        return ExtractionResponse(events=[])

    monkeypatch.setattr(sync_runner, "extract_events", fake_extract)

    await client.post("/api/v1/sync", headers=_auth(token))
    first = (await client.get("/api/v1/sync/status", headers=_auth(token))).json()
    await client.post("/api/v1/sync", headers=_auth(token))
    second = (await client.get("/api/v1/sync/status", headers=_auth(token))).json()

    assert extract_calls == ["m_real"]  # gated email NEVER hit Claude
    assert first["processed"] == 2      # but it still counted as processed
    assert second["to_process"] == 0    # and is not revisited next sync


async def test_failed_extraction_is_retried_next_sync(client, db, monkeypatch):
    """The marker must NOT suppress retries: a message whose extraction failed
    (transient Claude error) gets no marker and is re-attempted next sync."""
    from api.config.settings import settings as app_settings

    monkeypatch.setattr(app_settings, "sync_cooldown_seconds", 0)
    user, token = await _user_with_token(db)
    metadata = [{"message_id": "m1", "sender": "a@x.org", "subject": "S", "date": "Mon"}]
    monkeypatch.setattr(sync_runner, "fetch_recent_metadata", lambda email: metadata)
    monkeypatch.setattr(sync_runner, "fetch_message_bodies", lambda email, ids: {i: "practice on Thursday" for i in ids})

    extract_calls = []

    def flaky_extract(body, subject, sender, message_id="", email_date=""):
        extract_calls.append(message_id)
        if len(extract_calls) == 1:
            raise RuntimeError("transient API error")
        return ExtractionResponse(events=[])

    monkeypatch.setattr(sync_runner, "extract_events", flaky_extract)

    await client.post("/api/v1/sync", headers=_auth(token))  # fails → no marker
    await client.post("/api/v1/sync", headers=_auth(token))  # retries → succeeds
    await client.post("/api/v1/sync", headers=_auth(token))  # now skipped

    assert extract_calls == ["m1", "m1"]  # retried once, then never again


async def test_sync_cooldown_returns_429(client, db, monkeypatch):
    """A3 audit finding: repeated POST /sync triggered a full 30-day metadata
    scan each time. A per-user cooldown between completed syncs closes it."""
    from api.config.settings import settings as app_settings

    monkeypatch.setattr(app_settings, "sync_cooldown_seconds", 60)
    _, token = await _user_with_token(db)
    monkeypatch.setattr(sync_runner, "fetch_recent_metadata", lambda email: [])
    monkeypatch.setattr(sync_runner, "fetch_message_bodies", lambda email, ids: {})

    first = await client.post("/api/v1/sync", headers=_auth(token))
    second = await client.post("/api/v1/sync", headers=_auth(token))

    assert first.status_code == 202
    assert second.status_code == 429
    assert "Retry-After" in second.headers


async def test_sync_status_reports_to_process_during_run(client, db, monkeypatch):
    from api.services import sync_state
    from api.services.users import get_or_create_user
    # _user_with_token creates the user "parent@example.com"; re-fetch it so we
    # can seed a running state under the same id the JWT names.
    user = await get_or_create_user(db, "parent@example.com")
    _, token = await _user_with_token(db)
    sync_state.progress(user.id, messages_scanned=30, to_process=28, processed=12, items_created=3)

    resp = await client.get("/api/v1/sync/status", headers=_auth(token))

    body = resp.json()
    assert body["status"] == "running"
    assert body["to_process"] == 28
    assert body["processed"] == 12
    assert body["items_created"] == 3


async def test_run_sync_job_updates_processed_incrementally(db, session_factory, monkeypatch):
    # session_factory is the conftest fixture bound to the TEST SQLite engine
    # (a StaticPool shared with `db`), so the job sees the committed test user.
    # Do NOT use the production get_session_factory() — it binds to Railway.
    from api.services import sync_state
    from api.services.users import get_or_create_user
    from api.schemas.family_event import FamilyItem, ExtractionResponse

    user = await get_or_create_user(db, "inc@example.com")
    meta = [
        {"message_id": "a", "sender": "s@school.edu", "subject": "x", "date": ""},
        {"message_id": "b", "sender": "s@school.edu", "subject": "y", "date": ""},
    ]
    monkeypatch.setattr(sync_runner, "fetch_recent_metadata", lambda email: meta)
    monkeypatch.setattr(sync_runner, "fetch_message_bodies", lambda email, ids: {i: "practice on Thursday" for i in ids})
    # s@school.edu is not on the default blocklist, so both messages pass classify.

    # Record processed at each extract call to prove it increments mid-run.
    seen = []

    def fake_extract(*args, **kwargs):
        seen.append(sync_state.get_state(user.id).processed)
        return ExtractionResponse(events=[FamilyItem(item_type="action", action_required="do")])

    monkeypatch.setattr(sync_runner, "extract_events", fake_extract)

    sync_state.try_start(user.id)
    await sync_runner.run_sync_job(user.id, user.email, session_factory)

    # processed was 0 before the first item, 1 before the second.
    assert seen == [0, 1]
    final = sync_state.get_state(user.id)
    assert final.status == "done"
    assert final.to_process == 2


async def test_redact_pii_runs_off_the_event_loop(db, session_factory, monkeypatch):
    """Presidio's analyzer is CPU-bound spaCy work; on the event loop it stalls
    every concurrent request for the whole sync. It must go through
    asyncio.to_thread like its siblings (fetch_message_bodies, extract_events)."""
    import threading
    from types import SimpleNamespace

    from api.services import sync_state
    from api.services.users import get_or_create_user

    user = await get_or_create_user(db, "offloop@example.com")
    meta = [{"message_id": "t1", "sender": "s@school.edu", "subject": "x", "date": ""}]
    monkeypatch.setattr(sync_runner, "fetch_recent_metadata", lambda email: meta)
    monkeypatch.setattr(
        sync_runner, "fetch_message_bodies", lambda email, ids: {i: "practice on Thursday" for i in ids}
    )
    monkeypatch.setattr(
        sync_runner, "extract_events",
        lambda *a, **k: ExtractionResponse(events=[]),
    )

    redact_threads = []

    def fake_redact(text):
        redact_threads.append(threading.get_ident())
        return SimpleNamespace(redacted_text=text)

    monkeypatch.setattr(sync_runner, "redact_pii", fake_redact)

    sync_state.try_start(user.id)
    await sync_runner.run_sync_job(user.id, user.email, session_factory)

    assert redact_threads, "redact_pii was never called"
    assert all(t != threading.get_ident() for t in redact_threads)


async def test_failed_sync_reports_failed_status(client, db, monkeypatch):
    _, token = await _user_with_token(db)

    def boom(email):
        raise ValueError("gmail exploded")

    monkeypatch.setattr(sync_runner, "fetch_recent_metadata", boom)

    resp = await client.post("/api/v1/sync", headers=_auth(token))
    assert resp.status_code == 202

    status = (await client.get("/api/v1/sync/status", headers=_auth(token))).json()
    assert status["status"] == "failed"
    # Sanitized: no internal exception text leaks to the client.
    assert "exploded" not in (status.get("error") or "")


async def test_one_failing_extraction_does_not_kill_the_sync(client, db, monkeypatch):
    """A per-message extraction error (e.g. a transient Claude API failure —
    or 2026-07-15's invalid tool schema, which 400'd EVERY message and killed
    every sync) must skip that message and keep processing the rest. The
    failed message stays unsynced (no items row), so a later sync retries it.
    """
    _, token = await _user_with_token(db)

    metadata = [
        {"message_id": "m_bad", "sender": "a@ok.org", "subject": "Bad", "date": "Mon"},
        {"message_id": "m_good", "sender": "b@ok.org", "subject": "Good", "date": "Tue"},
    ]
    monkeypatch.setattr(sync_runner, "fetch_recent_metadata", lambda email: metadata)
    monkeypatch.setattr(
        sync_runner, "fetch_message_bodies",
        lambda email, ids: {mid: "practice on Thursday" for mid in ids},
    )

    def fake_extract(body, subject, sender, message_id="", email_date=""):
        if message_id == "m_bad":
            raise RuntimeError("claude 400")
        return ExtractionResponse(
            events=[FamilyItem(item_type="event", event_title="Kept", date="2026-07-16")]
        )

    monkeypatch.setattr(sync_runner, "extract_events", fake_extract)

    resp = await client.post("/api/v1/sync", headers=_auth(token))
    assert resp.status_code == 202

    status = (await client.get("/api/v1/sync/status", headers=_auth(token))).json()
    assert status["status"] == "done"
    assert status["items_created"] == 1

    listed = (await client.get("/api/v1/items", headers=_auth(token))).json()["items"]
    assert [i["event_title"] for i in listed] == ["Kept"]


async def test_reauth_required_surfaces_clean_message(client, db, monkeypatch):
    """A revoked/absent Gmail token (ReauthRequired) must fail the sync with a
    'sign in again' message via the specific handler — not the generic 'Sync
    failed' path whose _log.exception would log the traceback."""
    from api.services.google_token import ReauthRequired

    _, token = await _user_with_token(db)

    def needs_reauth(email):
        raise ReauthRequired

    monkeypatch.setattr(sync_runner, "fetch_recent_metadata", needs_reauth)

    resp = await client.post("/api/v1/sync", headers=_auth(token))
    assert resp.status_code == 202
    status = (await client.get("/api/v1/sync/status", headers=_auth(token))).json()
    assert status["status"] == "failed"
    assert status["error"] == "Please sign in again."
