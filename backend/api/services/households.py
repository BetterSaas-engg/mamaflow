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
from api.services.entitlements import member_limit

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
    return owner or user


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

    current = len(await members(db, household.id))
    open_invites = await _open_invites(db, household.id)
    # Count outstanding invitations against the cap too, or a Family owner
    # could mint ten codes and let ten people in.
    if current + len(open_invites) >= limit:
        raise MemberLimitReached(limit)

    code = _new_code()
    invite = HouseholdInvite(
        household_id=household.id,
        code_hash=_hash_code(code),
        expires_at=await _now() + datetime.timedelta(days=INVITE_TTL_DAYS),
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
    rows = await db.execute(
        select(HouseholdInvite).where(
            HouseholdInvite.code_hash == _hash_code(code),
            HouseholdInvite.accepted_at.is_(None),
            HouseholdInvite.revoked_at.is_(None),
            HouseholdInvite.deleted_at.is_(None),
            HouseholdInvite.expires_at > now,
        )
    )
    invite = rows.scalars().first()
    if invite is None:
        # One error for unknown/expired/used/revoked: distinguishing them tells
        # a guesser which codes exist.
        raise InviteInvalid

    household = await db.get(Household, invite.household_id)
    if household is None or household.deleted_at is not None:
        raise InviteInvalid

    owner = await db.get(User, household.owner_user_id)
    limit = member_limit(owner.tier if owner else None)
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
    "create_invite",
    "ensure_household",
    "leave_household",
    "members",
    "pending_invites",
    "plan_owner",
    "remove_member",
    "revoke_invite",
    "visible_user_ids",
]
