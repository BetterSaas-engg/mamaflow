"""Households: two parents, one plan, one shared calendar (D46).

The load-bearing property is the SHARING BOUNDARY. Members share extracted
items — that is the product — but never mailbox access: no member can read
another's raw mail, use their credentials, or disconnect their mailboxes.
These tests pin both halves, because widening either one silently would be a
privacy failure nobody would notice from the UI.
"""

import datetime

import pytest

from api.auth.jwt import create_access_token
from api.models.household import HouseholdInvite
from api.schemas.family_event import FamilyItem
from api.services.households import (
    AlreadyInHousehold,
    InviteInvalid,
    MemberLimitReached,
    NotHouseholdOwner,
    accept_invite,
    create_invite,
    leave_household,
    remove_member,
    visible_user_ids,
)
from api.services.items import list_items, persist_items
from api.services.mail_connections import ensure_connection, list_connections
from api.services.users import get_or_create_user


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _user(db, email, tier="free"):
    user = await get_or_create_user(db, email)
    user.tier = tier
    await db.commit()
    return user, create_access_token(subject=str(user.id), email=user.email)


async def _join(db, owner, member):
    _, code = await create_invite(db, owner)
    await accept_invite(db, member, code)


async def _item(db, user, message_id, title):
    return await persist_items(
        db, user, message_id,
        [FamilyItem(item_type="event", event_title=title, date="2026-08-10")],
    )


# --- the sharing boundary ---


async def test_members_see_each_others_items(db):
    """The shared family calendar — the entire point of the tier."""
    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, _ = await _user(db, "dad@example.com")
    await _join(db, mum, dad)
    await _item(db, mum, "m1", "Swimming lesson")
    await _item(db, dad, "d1", "Dentist")

    seen_by_dad = {i.event_title for i in await list_items(db, dad)}
    seen_by_mum = {i.event_title for i in await list_items(db, mum)}

    assert seen_by_dad == {"Swimming lesson", "Dentist"}
    assert seen_by_mum == {"Swimming lesson", "Dentist"}


async def test_a_solo_account_sees_only_its_own_items(db):
    mum, _ = await _user(db, "mum@example.com")
    stranger, _ = await _user(db, "stranger@example.com")
    await _item(db, mum, "m1", "Swimming lesson")
    await _item(db, stranger, "s1", "Not yours")

    assert {i.event_title for i in await list_items(db, mum)} == {"Swimming lesson"}


async def test_members_never_share_mailbox_access(db):
    """Sharing a calendar must not share credentials. Each parent keeps their
    own mailboxes; a household is not a key to someone else's inbox."""
    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, _ = await _user(db, "dad@example.com")
    await _join(db, mum, dad)
    await ensure_connection(db, mum, "google", "mum@example.com")
    await ensure_connection(db, dad, "yahoo", "dad@yahoo.com")

    assert [c.email for c in await list_connections(db, mum.id)] == ["mum@example.com"]
    assert [c.email for c in await list_connections(db, dad.id)] == ["dad@yahoo.com"]


async def test_leaving_stops_the_sharing_both_ways(db):
    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, _ = await _user(db, "dad@example.com")
    await _join(db, mum, dad)
    await _item(db, mum, "m1", "Swimming lesson")
    await _item(db, dad, "d1", "Dentist")

    await leave_household(db, dad)

    assert {i.event_title for i in await list_items(db, dad)} == {"Dentist"}
    assert {i.event_title for i in await list_items(db, mum)} == {"Swimming lesson"}


async def test_removing_a_member_unshares_but_deletes_nothing(db):
    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, _ = await _user(db, "dad@example.com")
    await _join(db, mum, dad)
    await _item(db, dad, "d1", "Dentist")

    assert await remove_member(db, mum, dad.id) is True

    # Dad keeps his own items; mum simply stops seeing them.
    assert {i.event_title for i in await list_items(db, dad)} == {"Dentist"}
    assert await list_items(db, mum) == []


# --- membership rules ---


async def test_family_allows_a_second_member_but_not_a_third(db):
    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, _ = await _user(db, "dad@example.com")
    await _join(db, mum, dad)
    third, _ = await _user(db, "third@example.com")

    with pytest.raises(MemberLimitReached):
        await create_invite(db, mum)


async def test_free_and_pro_cannot_invite_anyone(db):
    for tier in ("free", "pro"):
        owner, _ = await _user(db, f"{tier}@example.com", tier=tier)
        with pytest.raises(MemberLimitReached):
            await create_invite(db, owner)


async def test_outstanding_invites_count_against_the_limit(db):
    """Otherwise an owner could mint several codes and let several people in."""
    mum, _ = await _user(db, "mum@example.com", tier="family")
    await create_invite(db, mum)

    with pytest.raises(MemberLimitReached):
        await create_invite(db, mum)


async def test_a_member_cannot_invite_further_people(db):
    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, _ = await _user(db, "dad@example.com")
    await _join(db, mum, dad)

    with pytest.raises(NotHouseholdOwner):
        await create_invite(db, dad)


async def test_the_owner_cannot_abandon_their_own_household(db):
    """Leaving would strand the other member on a plan they don't own."""
    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, _ = await _user(db, "dad@example.com")
    await _join(db, mum, dad)

    with pytest.raises(NotHouseholdOwner):
        await leave_household(db, mum)


async def test_a_member_inherits_the_owners_plan(db):
    """One household, one bill — a Family member must not see the free cap."""
    from api.services.mail_connections import mailbox_usage

    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, _ = await _user(db, "dad@example.com")  # own tier is free
    await _join(db, mum, dad)

    _, limit, _ = await mailbox_usage(db, dad)

    assert limit == 2


# --- invite codes ---


async def test_a_code_works_once(db):
    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, _ = await _user(db, "dad@example.com")
    _, code = await create_invite(db, mum)
    await accept_invite(db, dad, code)

    later, _ = await _user(db, "later@example.com")
    with pytest.raises(InviteInvalid):
        await accept_invite(db, later, code)


async def test_the_plaintext_code_is_never_stored(db):
    """A code grants sight of a household's calendar; reading the database
    must not hand out working invitations."""
    from sqlalchemy import select

    mum, _ = await _user(db, "mum@example.com", tier="family")
    _, code = await create_invite(db, mum)

    rows = await db.execute(select(HouseholdInvite.code_hash))
    stored = [r[0] for r in rows]

    assert code not in stored
    assert all(len(h) == 64 for h in stored)  # sha256 hex


async def test_an_expired_code_is_refused(db):
    from sqlalchemy import select

    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, _ = await _user(db, "dad@example.com")
    _, code = await create_invite(db, mum)
    rows = await db.execute(select(HouseholdInvite))
    invite = rows.scalars().first()
    invite.expires_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
    await db.commit()

    with pytest.raises(InviteInvalid):
        await accept_invite(db, dad, code)


async def test_a_wrong_code_is_refused(db):
    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, _ = await _user(db, "dad@example.com")
    await create_invite(db, mum)

    with pytest.raises(InviteInvalid):
        await accept_invite(db, dad, "AAAAAAAA")


async def test_you_cannot_join_two_households(db):
    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, _ = await _user(db, "dad@example.com")
    await _join(db, mum, dad)
    other, _ = await _user(db, "other@example.com", tier="family")
    _, code = await create_invite(db, other)

    with pytest.raises(AlreadyInHousehold):
        await accept_invite(db, dad, code)


# --- API ---


async def test_household_endpoints_end_to_end(client, db):
    mum, mum_token = await _user(db, "mum@example.com", tier="family")
    dad, dad_token = await _user(db, "dad@example.com")

    created = await client.post(
        "/api/v1/account/household/invites", headers=_auth(mum_token)
    )
    assert created.status_code == 201
    code = created.json()["code"]

    joined = await client.post(
        "/api/v1/account/household/invites/accept",
        headers=_auth(dad_token),
        json={"code": code},
    )
    assert joined.status_code == 200
    body = joined.json()
    assert body["exists"] is True
    assert {m["email"] for m in body["members"]} == {
        "mum@example.com",
        "dad@example.com",
    }
    assert body["is_owner"] is False  # dad joined, mum owns

    # Dad leaves by removing himself.
    left = await client.delete(
        f"/api/v1/account/household/members/{dad.id}", headers=_auth(dad_token)
    )
    assert left.status_code == 204


async def test_a_member_cannot_remove_the_owner(client, db):
    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, dad_token = await _user(db, "dad@example.com")
    await _join(db, mum, dad)

    resp = await client.delete(
        f"/api/v1/account/household/members/{mum.id}", headers=_auth(dad_token)
    )

    assert resp.status_code == 403


async def test_a_free_owner_is_told_the_plan_limit(client, db):
    _, token = await _user(db, "solo@example.com", tier="free")

    resp = await client.post(
        "/api/v1/account/household/invites", headers=_auth(token)
    )

    assert resp.status_code == 402


async def test_household_endpoints_require_auth(client):
    assert (await client.get("/api/v1/account/household")).status_code == 401
    assert (
        await client.post("/api/v1/account/household/invites")
    ).status_code == 401


async def test_visible_ids_is_the_single_definition_of_visibility(db):
    """Every read must go through this, so a new query can't widen sharing."""
    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, _ = await _user(db, "dad@example.com")

    assert await visible_user_ids(db, mum) == [mum.id]

    await _join(db, mum, dad)
    await db.refresh(mum)

    assert set(await visible_user_ids(db, mum)) == {mum.id, dad.id}
