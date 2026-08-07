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


async def test_asking_again_replaces_the_code_rather_than_adding_one(db):
    """At most one live code per household — that is the real protection
    against minting several. And an owner whose partner never used the first
    code must not be locked out for the full 14-day TTL."""
    mum, _ = await _user(db, "mum@example.com", tier="family")
    _, first = await create_invite(db, mum)
    _, second = await create_invite(db, mum)

    dad, _ = await _user(db, "dad@example.com")
    with pytest.raises(InviteInvalid):
        await accept_invite(db, dad, first)  # superseded

    await accept_invite(db, dad, second)
    assert dad.household_id is not None


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

    assert limit == 3  # the plan's three shared mailboxes (D47)


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


# --- Audit follow-ups (2026-07-31 security review) ---


async def test_deleting_your_account_severs_the_household(db):
    """Deletion soft-deletes the row, and a later sign-in REACTIVATES it. If
    household_id survived that, signing back in silently restored sight of the
    other person's calendar — no invite, no accept, no notice to them."""
    from api.services.account import delete_account

    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, _ = await _user(db, "dad@example.com")
    await _join(db, mum, dad)
    await _item(db, mum, "m1", "Swimming lesson")

    await delete_account(db, dad)

    assert dad.household_id is None
    # Reactivate exactly as a real sign-in would.
    dad_again = await get_or_create_user(db, "dad@example.com")
    assert dad_again.household_id is None
    assert await list_items(db, dad_again) == []


async def test_reactivation_alone_never_restores_a_membership(db):
    """Belt and braces: even if a row somehow kept its household_id, coming
    back from deletion must not re-share."""
    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, _ = await _user(db, "dad@example.com")
    await _join(db, mum, dad)
    dad.deleted_at = datetime.datetime.now(datetime.UTC)
    await db.commit()  # household_id deliberately left intact

    revived = await get_or_create_user(db, "dad@example.com")

    assert revived.household_id is None


async def test_the_owner_deleting_dissolves_the_household(db):
    """The survivor would otherwise inherit a deleted owner's plan forever with
    no way to transfer or leave it."""
    from api.services.account import delete_account
    from api.services.mail_connections import mailbox_usage

    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, _ = await _user(db, "dad@example.com")
    await _join(db, mum, dad)

    await delete_account(db, mum)
    await db.refresh(dad)

    assert dad.household_id is None
    # And he's back on his own (free) plan, not the deleted owner's Family one.
    _, limit, _ = await mailbox_usage(db, dad)
    assert limit == 1


async def test_a_deleted_owner_stops_conferring_their_plan(db):
    """Defence in depth for the same thing, via plan_owner directly."""
    from api.services.households import plan_owner

    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, _ = await _user(db, "dad@example.com")
    await _join(db, mum, dad)
    mum.deleted_at = datetime.datetime.now(datetime.UTC)
    await db.commit()

    assert (await plan_owner(db, dad)).tier == "free"


async def test_deleting_an_owner_kills_their_outstanding_invites(db):
    from api.services.account import delete_account
    from api.services.households import pending_invites

    mum, _ = await _user(db, "mum@example.com", tier="family")
    household_id = None
    _, code = await create_invite(db, mum)
    household_id = mum.household_id

    await delete_account(db, mum)

    assert await pending_invites(db, household_id) == []
    stranger, _ = await _user(db, "stranger@example.com")
    with pytest.raises(InviteInvalid):
        await accept_invite(db, stranger, code)


async def test_an_owner_can_revoke_a_code_they_shared_by_mistake(client, db):
    from sqlalchemy import select

    mum, mum_token = await _user(db, "mum@example.com", tier="family")
    created = await client.post(
        "/api/v1/account/household/invites", headers=_auth(mum_token)
    )
    code = created.json()["code"]
    rows = await db.execute(select(HouseholdInvite.id))
    invite_id = rows.scalars().first()

    resp = await client.delete(
        f"/api/v1/account/household/invites/{invite_id}", headers=_auth(mum_token)
    )
    assert resp.status_code == 204

    dad, _ = await _user(db, "dad@example.com")
    with pytest.raises(InviteInvalid):
        await accept_invite(db, dad, code)


async def test_a_member_cannot_revoke_invites(client, db):
    import uuid as _uuid

    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, dad_token = await _user(db, "dad@example.com")
    await _join(db, mum, dad)

    # Ownership is checked before the invite is even looked up, so any id
    # exercises the rule — and the household is full, so no second invite
    # could exist to use here anyway.
    resp = await client.delete(
        f"/api/v1/account/household/invites/{_uuid.uuid4()}",
        headers=_auth(dad_token),
    )

    assert resp.status_code == 403


async def test_a_soft_deleted_member_drops_out_of_visibility(db):
    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, _ = await _user(db, "dad@example.com")
    await _join(db, mum, dad)
    await _item(db, dad, "d1", "Dentist")

    dad.deleted_at = datetime.datetime.now(datetime.UTC)
    await db.commit()

    assert await list_items(db, mum) == []


async def test_the_reminder_digest_covers_the_shared_calendar(db):
    """The digest must match what the app shows, or a parent gets a
    "tomorrow's schedule" push that silently omits half of tomorrow."""
    import datetime as dt

    from api.services.reminders import tomorrow_events

    mum, _ = await _user(db, "mum@example.com", tier="family")
    dad, _ = await _user(db, "dad@example.com")
    await _join(db, mum, dad)
    tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    await persist_items(
        db, dad, "d1",
        [FamilyItem(item_type="event", event_title="Dentist", date=tomorrow)],
    )

    titles = {i.event_title for i in await tomorrow_events(db, mum, tomorrow)}

    assert "Dentist" in titles
