"""Households: two parents, one plan, one shared calendar (D46).

**What is shared, and what is not.** Members see each other's extracted ITEMS —
that is the whole point of a shared family calendar. Members never share
mailbox access: each keeps their own logins, their own connections and their
own credentials, and no member can read another's raw mail or disconnect their
mailboxes.

That sharing is a real privacy decision, not a technicality. Since D37 the
extractor deliberately captures *all* appointments, including work meetings, so
joining a household means a partner sees events derived from your email. It is
therefore opt-in on BOTH sides — the owner invites, the other person accepts —
and the accept response states plainly what becomes visible.

The plan lives on the OWNER's user row; members inherit it. One tier, one bill.
"""

import datetime
import hashlib
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.household import Household, HouseholdInvite
from api.models.user import User
from api.services.entitlements import higher_tier, member_limit
from api.services.subscriptions import effective_tier

INVITE_TTL_DAYS = 14


class HouseholdError(Exception):
    """Base for household problems the caller can act on."""


class MemberLimitReached(HouseholdError):
    def __init__(self, limit: int) -> None:
        super().__init__(f"plan allows {limit} member(s)")
        self.limit = limit


class NotHouseholdOwner(HouseholdError):
    pass


class InviteInvalid(HouseholdError):
    """Unknown, expired, revoked, or already-used code."""


class AlreadyInHousehold(HouseholdError):
    pass


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


def _new_code() -> str:
    """A short, human-shareable code. Read aloud or typed, not clicked.

    ~10^9 possibilities over a 14-day window with single-use redemption; the
    accept endpoint is the brute-force surface and is throttled there.
    """
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I/O/0/1 lookalikes
    return "".join(secrets.choice(alphabet) for _ in range(8))


async def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


async def members(db: AsyncSession, household_id) -> list[User]:
    rows = await db.execute(
        select(User)
        .where(User.household_id == household_id, User.deleted_at.is_(None))
        .order_by(User.created_at)
    )
    return list(rows.scalars())


async def visible_user_ids(db: AsyncSession, user: User) -> list[uuid.UUID]:
    """Whose items this user may see.

    The single place that answers it, so a new query can't accidentally widen
    or narrow visibility. Solo accounts (everyone today) see only their own.
    """
    if user.household_id is None:
        return [user.id]
    return [m.id for m in await members(db, user.household_id)]


async def plan_owner(db: AsyncSession, user: User) -> User:
    """Whose tier applies to this user — their household's owner, or
    themselves. Members inherit the owner's plan: one household, one bill."""
    if user.household_id is None:
        return user
    household = await db.get(Household, user.household_id)
    if household is None:
        return user
    owner = await db.get(User, household.owner_user_id)
    # A soft-deleted owner must not keep conferring their plan.
    if owner is None or owner.deleted_at is not None:
        return user
    return owner


async def plan_tier(db: AsyncSession, user: User) -> str:
    """The tier that actually governs this user — the single answer.

    Takes the MORE GENEROUS of the household owner's tier and the user's own,
    rather than just the owner's. The case that forces it: a household MEMBER
    may be the one who paid. Every entitlement read routes through plan_owner,
    so without the max a member who bought Family would be served the owner's
    free allowance — they paid and got nothing, with nothing in the UI to
    explain it.

    Consequence accepted: a household whose member is the payer keeps the plan
    if that member leaves, and the owner drops back to their own tier. That is
    right — one bill, whoever pays it.
    """
    owner = await plan_owner(db, user)
    if owner.id == user.id:
        return effective_tier(user)
    return higher_tier(effective_tier(owner), effective_tier(user))


async def ensure_household(db: AsyncSession, owner: User) -> Household:
    """The user's household, created on first use with them as owner."""
    if owner.household_id is not None:
        existing = await db.get(Household, owner.household_id)
        if existing is not None:
            return existing
    household = Household(owner_user_id=owner.id)
    db.add(household)
    await db.flush()
    owner.household_id = household.id
    await db.commit()
    return household


async def create_invite(db: AsyncSession, owner: User) -> tuple[HouseholdInvite, str]:
    """Invite a second parent. Returns (invite, plaintext code).

    The plaintext is returned ONCE and never stored — only its hash is kept, so
    a database read cannot hand out working invitations.
    """
    limit = member_limit(owner.tier)
    household = await ensure_household(db, owner)
    if household.owner_user_id != owner.id:
        # A member cannot invite: the owner holds the plan and the bill.
        raise NotHouseholdOwner

    # Asking for a code again REPLACES the outstanding one rather than adding
    # to it. Two reasons: it is what "send it again" means to a user, and it
    # keeps at most one live code per household, which is the actual protection
    # against an owner minting several and letting several people in.
    #
    # It also avoids a trap: counting stale invites against the cap meant an
    # owner whose partner never used the first code was locked out of issuing
    # another for the full 14-day TTL.
    now = await _now()
    for stale in await _open_invites(db, household.id):
        stale.revoked_at = now

    current = len(await members(db, household.id))
    if current + 1 > limit:
        raise MemberLimitReached(limit)

    code = _new_code()
    invite = HouseholdInvite(
        household_id=household.id,
        code_hash=_hash_code(code),
        expires_at=now + datetime.timedelta(days=INVITE_TTL_DAYS),
    )
    db.add(invite)
    await db.commit()
    return invite, code


async def _open_invites(db: AsyncSession, household_id) -> list[HouseholdInvite]:
    now = await _now()
    rows = await db.execute(
        select(HouseholdInvite).where(
            HouseholdInvite.household_id == household_id,
            HouseholdInvite.accepted_at.is_(None),
            HouseholdInvite.revoked_at.is_(None),
            HouseholdInvite.deleted_at.is_(None),
            HouseholdInvite.expires_at > now,
        )
    )
    return list(rows.scalars())


async def accept_invite(db: AsyncSession, user: User, code: str) -> Household:
    """Join the household the code belongs to."""
    if user.household_id is not None:
        raise AlreadyInHousehold

    now = await _now()
    # Lock the invite row for the whole check-then-act. Without it, two
    # concurrent redemptions of the same code both saw accepted_at IS NULL and
    # both succeeded — a single-use code consumed twice, and the member cap
    # blown past (2026-07-31 audit BLOCK). Same precedent as the mailbox cap in
    # mail_connections. No-op on SQLite, which serializes writes anyway.
    rows = await db.execute(
        select(HouseholdInvite)
        .where(
            HouseholdInvite.code_hash == _hash_code(code),
            HouseholdInvite.accepted_at.is_(None),
            HouseholdInvite.revoked_at.is_(None),
            HouseholdInvite.deleted_at.is_(None),
            HouseholdInvite.expires_at > now,
        )
        .with_for_update()
    )
    invite = rows.scalars().first()
    if invite is None:
        # One error for unknown/expired/used/revoked: distinguishing them tells
        # a guesser which codes exist.
        raise InviteInvalid

    household = await db.get(Household, invite.household_id)
    if household is None or household.deleted_at is not None:
        raise InviteInvalid

    # Lock the household too: two DIFFERENT codes redeemed at once would
    # otherwise both pass the member count below.
    await db.execute(
        select(Household.id).where(Household.id == household.id).with_for_update()
    )
    owner = await db.get(User, household.owner_user_id)
    limit = member_limit(
        owner.tier if owner is not None and owner.deleted_at is None else None
    )
    if len(await members(db, household.id)) >= limit:
        # The plan may have been downgraded since the code was issued.
        raise MemberLimitReached(limit)

    user.household_id = household.id
    invite.accepted_at = now
    invite.accepted_by_user_id = user.id
    await db.commit()
    return household


async def revoke_invite(db: AsyncSession, owner: User, invite_id) -> bool:
    household = await db.get(Household, owner.household_id) if owner.household_id else None
    if household is None or household.owner_user_id != owner.id:
        raise NotHouseholdOwner
    invite = await db.get(HouseholdInvite, invite_id)
    if invite is None or invite.household_id != household.id or not invite.is_open:
        return False
    invite.revoked_at = await _now()
    await db.commit()
    return True


async def leave_household(db: AsyncSession, user: User) -> None:
    """Leave, losing sight of the household's shared items.

    The owner leaving would strand the other member on a plan they don't own,
    so the owner must remove the member first (or delete their account, which
    is a separate flow).
    """
    if user.household_id is None:
        return
    household = await db.get(Household, user.household_id)
    if household is not None and household.owner_user_id == user.id:
        raise NotHouseholdOwner
    user.household_id = None
    await db.commit()


async def remove_member(db: AsyncSession, owner: User, member_id) -> bool:
    """Owner removes another member. Their items stop being visible to the
    household immediately, and vice versa — nothing is deleted, only unshared.
    """
    if owner.household_id is None:
        raise NotHouseholdOwner
    household = await db.get(Household, owner.household_id)
    if household is None or household.owner_user_id != owner.id:
        raise NotHouseholdOwner
    if member_id == owner.id:
        raise NotHouseholdOwner  # the owner cannot remove themselves
    member = await db.get(User, member_id)
    if member is None or member.household_id != household.id:
        return False
    member.household_id = None
    await db.commit()
    return True


async def pending_invites(db: AsyncSession, household_id) -> list[HouseholdInvite]:
    return await _open_invites(db, household_id)


# Re-exported for callers that only need the filter shape.
__all__ = [
    "AlreadyInHousehold",
    "HouseholdError",
    "InviteInvalid",
    "MemberLimitReached",
    "NotHouseholdOwner",
    "accept_invite",
    "dissolve_or_leave",
    "create_invite",
    "ensure_household",
    "leave_household",
    "members",
    "pending_invites",
    "plan_owner",
    "plan_tier",
    "remove_member",
    "revoke_invite",
    "visible_user_ids",
]


async def dissolve_or_leave(db: AsyncSession, user: User) -> None:
    """Sever this user's household ties as part of account deletion.

    Without this, deletion left `users.household_id` pointing at the household
    and `get_or_create_user` reactivates a soft-deleted row on the next
    sign-in — silently restoring full calendar sharing with no invite, no
    accept, and no notice to the other member (2026-07-31 audit BLOCK). It also
    bypassed the member cap entirely, since nothing routed through
    accept_invite.

    An owner deleting DISSOLVES the household: the remaining member would
    otherwise keep inheriting a deleted owner's plan with no way to transfer
    it. Everyone is released to a solo account, which is the state they can
    actually manage.
    """
    if user.household_id is None:
        return
    household = await db.get(Household, user.household_id)
    user.household_id = None
    if household is None:
        return
    if household.owner_user_id != user.id:
        return

    now = await _now()
    for member in await members(db, household.id):
        member.household_id = None
    for invite in await _open_invites(db, household.id):
        invite.revoked_at = now
    household.deleted_at = now
