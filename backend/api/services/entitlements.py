"""What a tier is allowed to do — the single source of truth for plan limits.

Deliberately one module with no DB or HTTP knowledge, so the limits can be read
and tested in isolation and there is exactly one place to change when pricing
moves. Every caller asks this module; nothing hardcodes a number.

Tiers (D44):
  free    1 mailbox,  1 member   — ad-supported
  pro     2 mailboxes, 1 member  — ad-free
  family  2 mailboxes PER MEMBER, 2 members (e.g. both parents), ad-free

Note the shape: the mailbox cap is always PER USER (1 / 2 / 2). Family's extra
allowance is a second *member* in the household, each with their own login and
their own 2 mailboxes — not a bigger pile of mailboxes on one account. That
keeps the cap check identical in all three tiers and confines the household
concept to member management.
"""

import dataclasses

FREE = "free"
PRO = "pro"
FAMILY = "family"

DEFAULT_TIER = FREE


@dataclasses.dataclass(frozen=True)
class Entitlements:
    """What one user on this tier may do."""

    tier: str
    # Mailboxes this ONE user may connect (their own logins/app passwords).
    mailboxes: int
    # Adults who can share the household, each with their own account.
    members: int
    # Ads are the free tier's price (D21); paying removes them.
    ads: bool


_TIERS: dict[str, Entitlements] = {
    FREE: Entitlements(tier=FREE, mailboxes=1, members=1, ads=True),
    PRO: Entitlements(tier=PRO, mailboxes=2, members=1, ads=False),
    FAMILY: Entitlements(tier=FAMILY, mailboxes=2, members=2, ads=False),
}

TIERS = tuple(_TIERS)


def entitlements_for(tier: str | None) -> Entitlements:
    """Limits for `tier`, falling back to free for anything unrecognised.

    Fail *closed* on the allowance but never raise: an unknown tier means a
    stale row or a billing bug, and the safe reading is "no paid allowance",
    not a 500 that locks the user out of their own calendar. Same
    coerce-don't-reject stance as D34's event_type.
    """
    return _TIERS.get(tier or DEFAULT_TIER, _TIERS[DEFAULT_TIER])


def mailbox_limit(tier: str | None) -> int:
    return entitlements_for(tier).mailboxes


def member_limit(tier: str | None) -> int:
    return entitlements_for(tier).members


def can_connect_another_mailbox(tier: str | None, current_count: int) -> bool:
    """Whether a user on `tier` who already has `current_count` mailboxes may
    connect one more."""
    return current_count < mailbox_limit(tier)
