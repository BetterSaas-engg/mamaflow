"""Tests for the JWT-gated sync endpoints + POST /sync (Phase C, req #6).

Gmail and the Claude extractor are mocked — tests never hit live APIs.
The load-bearing assertion: a blocked sender's body is never fetched.
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


async def test_extract_requires_auth(client):
    resp = await client.get("/api/v1/sync/extract")
    assert resp.status_code == 401


async def test_preview_requires_auth(client):
    resp = await client.get("/api/v1/sync/preview")
    assert resp.status_code == 401


async def test_preview_filtered_requires_auth(client):
    resp = await client.get("/api/v1/sync/preview-filtered")
    assert resp.status_code == 401


async def test_sync_requires_auth(client):
    resp = await client.post("/api/v1/sync")
    assert resp.status_code == 401


async def test_sync_persists_items_and_never_fetches_blocked_bodies(client, db, monkeypatch):
    user, token = await _user_with_token(db)
    db.add(SenderBlocklist(domain="blocked.com", category="financial", reason="test"))
    await db.commit()

    metadata = [
        {"message_id": "m_ok", "sender": "school@allowed.org", "subject": "Soccer", "date": "Mon"},
        {"message_id": "m_block", "sender": "billing@blocked.com", "subject": "Invoice", "date": "Tue"},
    ]
    monkeypatch.setattr(sync_router, "fetch_recent_metadata", lambda email: metadata)

    captured = {}

    def fake_bodies(email, ids):
        captured["ids"] = list(ids)
        return {mid: "body text" for mid in ids}

    monkeypatch.setattr(sync_router, "fetch_message_bodies", fake_bodies)

    def fake_extract(body, subject, sender, message_id=""):
        return ExtractionResponse(
            events=[FamilyItem(item_type="event", event_title="Soccer", date="2026-06-20")]
        )

    monkeypatch.setattr(sync_router, "extract_events", fake_extract)

    resp = await client.post("/api/v1/sync", headers=_auth(token))

    assert resp.status_code == 200
    body = resp.json()
    assert body["messages_scanned"] == 2
    assert body["blocked"] == 1
    assert body["items_created"] == 1

    # Metadata-first invariant: the blocked sender's body was NOT fetched.
    assert captured["ids"] == ["m_ok"]

    # Items were persisted and are listable.
    listed = await client.get("/api/v1/items", headers=_auth(token))
    assert len(listed.json()["items"]) == 1


async def test_sync_is_idempotent_on_resync(client, db, monkeypatch):
    user, token = await _user_with_token(db)
    metadata = [{"message_id": "m1", "sender": "a@x.org", "subject": "S", "date": "Mon"}]
    monkeypatch.setattr(sync_router, "fetch_recent_metadata", lambda email: metadata)
    monkeypatch.setattr(sync_router, "fetch_message_bodies", lambda email, ids: {i: "b" for i in ids})
    monkeypatch.setattr(
        sync_router, "extract_events",
        lambda body, subject, sender, message_id="": ExtractionResponse(
            events=[FamilyItem(item_type="event", event_title="X")]
        ),
    )

    first = await client.post("/api/v1/sync", headers=_auth(token))
    second = await client.post("/api/v1/sync", headers=_auth(token))

    assert first.json()["items_created"] == 1
    assert second.json()["items_created"] == 0  # already synced
    listed = await client.get("/api/v1/items", headers=_auth(token))
    assert len(listed.json()["items"]) == 1
