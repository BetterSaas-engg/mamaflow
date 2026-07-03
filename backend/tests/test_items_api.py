"""Tests for the JWT-scoped items API (Phase B, requirement #3)."""

from api.auth.jwt import create_access_token
from api.schemas.family_event import FamilyItem
from api.services.items import persist_items
from api.services.users import get_or_create_user


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _user_with_token(db, email="parent@example.com"):
    user = await get_or_create_user(db, email)
    return user, create_access_token(subject=str(user.id), email=user.email)


async def test_get_items_requires_auth(client):
    resp = await client.get("/api/v1/items")
    assert resp.status_code == 401


async def test_get_items_returns_user_items(client, db):
    user, token = await _user_with_token(db)
    await persist_items(
        db, user, "m1",
        [FamilyItem(item_type="event", event_title="Soccer", date="2026-06-20")],
    )

    resp = await client.get("/api/v1/items", headers=_auth(token))

    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["event_title"] == "Soccer"
    assert item["date"] == "2026-06-20"
    assert item["status"] == "open"
    assert item["id"]


async def test_get_items_filters_by_date_range(client, db):
    user, token = await _user_with_token(db)
    await persist_items(db, user, "m1", [
        FamilyItem(item_type="event", event_title="June", date="2026-06-15"),
        FamilyItem(item_type="event", event_title="July", date="2026-07-15"),
    ])

    resp = await client.get(
        "/api/v1/items?from=2026-06-01&to=2026-06-30", headers=_auth(token)
    )

    assert [i["event_title"] for i in resp.json()["items"]] == ["June"]


async def test_patch_updates_status(client, db):
    user, token = await _user_with_token(db)
    [item] = await persist_items(
        db, user, "m1", [FamilyItem(item_type="action", event_title="Register")]
    )

    resp = await client.patch(
        f"/api/v1/items/{item.id}", json={"status": "done"}, headers=_auth(token)
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "done"


async def test_patch_cannot_touch_another_users_item(client, db):
    alice, _ = await _user_with_token(db, "alice@example.com")
    _, bob_token = await _user_with_token(db, "bob@example.com")
    [item] = await persist_items(
        db, alice, "m1", [FamilyItem(item_type="action", event_title="Secret")]
    )

    resp = await client.patch(
        f"/api/v1/items/{item.id}", json={"status": "done"}, headers=_auth(bob_token)
    )

    assert resp.status_code == 404


async def test_patch_rejects_invalid_status(client, db):
    user, token = await _user_with_token(db)
    [item] = await persist_items(
        db, user, "m1", [FamilyItem(item_type="action", event_title="X")]
    )

    resp = await client.patch(
        f"/api/v1/items/{item.id}", json={"status": "banana"}, headers=_auth(token)
    )

    assert resp.status_code == 422
