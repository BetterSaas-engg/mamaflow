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
from api.routers import sync as sync_router
from api.schemas.family_event import ExtractionResponse, FamilyItem
from api.services.users import get_or_create_user


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _user_with_token(db, email="parent@example.com"):
    user = await get_or_create_user(db, email)
    return user, create_access_token(subject=str(user.id), email=user.email)


async def test_sync_requires_auth(client):
    assert (await client.post("/api/v1/sync")).status_code == 401
    assert (await client.get("/api/v1/sync/status")).status_code == 401


async def test_preview_requires_auth(client):
    assert (await client.get("/api/v1/sync/preview")).status_code == 401
    assert (await client.get("/api/v1/sync/preview-filtered")).status_code == 401
    assert (await client.get("/api/v1/sync/extract")).status_code == 401


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
    monkeypatch.setattr(sync_router, "fetch_recent_metadata", lambda email: metadata)

    fetched_ids = []

    def fake_bodies(email, ids):
        fetched_ids.extend(ids)
        return {mid: "body" for mid in ids}

    monkeypatch.setattr(sync_router, "fetch_message_bodies", fake_bodies)
    monkeypatch.setattr(
        sync_router, "extract_events",
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
    user, token = await _user_with_token(db)
    metadata = [{"message_id": "m1", "sender": "a@x.org", "subject": "S", "date": "Mon"}]
    monkeypatch.setattr(sync_router, "fetch_recent_metadata", lambda email: metadata)

    body_calls = []
    extract_calls = []

    def fake_bodies(email, ids):
        body_calls.append(list(ids))
        return {i: "b" for i in ids}

    def fake_extract(body, subject, sender, message_id="", email_date=""):
        extract_calls.append(message_id)
        return ExtractionResponse(events=[FamilyItem(item_type="event", event_title="X")])

    monkeypatch.setattr(sync_router, "fetch_message_bodies", fake_bodies)
    monkeypatch.setattr(sync_router, "extract_events", fake_extract)

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


async def test_failed_sync_reports_failed_status(client, db, monkeypatch):
    _, token = await _user_with_token(db)

    def boom(email):
        raise ValueError("gmail exploded")

    monkeypatch.setattr(sync_router, "fetch_recent_metadata", boom)

    resp = await client.post("/api/v1/sync", headers=_auth(token))
    assert resp.status_code == 202

    status = (await client.get("/api/v1/sync/status", headers=_auth(token))).json()
    assert status["status"] == "failed"
    # Sanitized: no internal exception text leaks to the client.
    assert "exploded" not in (status.get("error") or "")
