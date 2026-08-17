"""What a tier is allowed to do — the single source of truth for plan limits.

Deliberately one module with no DB or HTTP knowledge, so the limits can be read
and tested in isolation and there is exactly one place to change when pricing
moves. Every caller asks this module; nothing hardcodes a number.

Tiers (D44, revised D47):
  free    1 mailbox,  1 member   — ad-supported
  pro     2 mailboxes, 1 member  — ad-free
  family  3 mailboxes, 2 members (e.g. both parents), ad-free

**`mailboxes` is the cap across the whole PLAN, not per person.** For a solo
account the plan is just them; for a Family the three are shared between the two
parents however they like.

Revised from "2 per member" (D47): billing 4 mailboxes on Family against Pro's 2
made Family cost ~2x Pro to serve, so at any price under 2x Pro the premium tier
earned less per user than the mid tier — backwards. Three shared mailboxes is
1.5x Pro's cost and matches how households actually look: two adults with a main
inbox each, plus one shared or work address.
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
    # Mailboxes across the whole PLAN — shared by every member of the
    # household, not a per-person allowance.
    mailboxes: int
    # Adults who can share the household, each with their own account.
    members: int
    # Ads are the free tier's price (D21); paying removes them.
    ads: bool


_TIERS: dict[str, Entitlements] = {
    FREE: Entitlements(tier=FREE, mailboxes=1, members=1, ads=True),
    PRO: Entitlements(tier=PRO, mailboxes=2, members=1, ads=False),
    FAMILY: Entitlements(tier=FAMILY, mailboxes=3, members=2, ads=False),
}

TIERS = tuple(_TIERS)

# Ascending generosity. Declared once so nothing hardcodes an ordering, and so
# adding a tier is a single edit here.
TIER_RANK = (FREE, PRO, FAMILY)


def higher_tier(a: str | None, b: str | None) -> str:
    """The more generous of two tiers.

    Order-independent by construction, which is what makes it safe to combine
    tiers that arrive from different places (a household owner and a member, or
    two overlapping subscriptions) without caring which was seen first.
    Unrecognised values normalise to free via entitlements_for.
    """
    rank_a = TIER_RANK.index(entitlements_for(a).tier)
    rank_b = TIER_RANK.index(entitlements_for(b).tier)
    return TIER_RANK[max(rank_a, rank_b)]


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
    """Whether a plan on `tier` already using `current_count` mailboxes may
    connect one more. `current_count` is the count across the whole plan."""
    return current_count < mailbox_limit(tier)
