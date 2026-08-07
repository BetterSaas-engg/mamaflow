"""`users.tier` as a projection of `subscriptions` (D47).

The entitling predicate below is the whole design, and each line of it is a
known revenue bug that this category is famous for. Read it before changing it.

**D19 note for reviewers:** `scripts/firewall-guard.sh` keys on file *paths*
(`*ads/*`, `*ad_*.dart`, …), so it will NOT catch a leak from this module.
Subscription state, tier and churn signals must never reach the ad layer as
targeting parameters — that is a manual review rule here.
"""

import datetime
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.subscription import Subscription
from api.models.user import User
from api.services.entitlements import (
    DEFAULT_TIER,
    FREE,
    PRO,
    TIERS,
    entitlements_for,
    higher_tier,
)

_log = logging.getLogger(__name__)

# Statuses that entitle. `in_retry` deliberately does NOT: Apple's billing
# retry runs up to 60 days with the user unentitled, but the row survives, so a
# renewal arriving weeks later re-grants with no special case.
ENTITLING_STATUSES = frozenset({"active", "in_grace"})


def _aware(value: datetime.datetime | None) -> datetime.datetime | None:
    """Rows written before a column was tz-aware can come back naive."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value


def access_end(sub: Subscription) -> datetime.datetime | None:
    """When access actually stops — the later of the paid period and any grace."""
    ends = [d for d in (_aware(sub.current_period_end), _aware(sub.grace_period_end)) if d]
    return max(ends) if ends else None


def is_entitling(
    sub: Subscription,
    now: datetime.datetime,
    expected_environment: str = "production",
) -> bool:
    """Whether this subscription currently grants its tier.

    Four rules, each one a bug that has cost other people real money:

    1. **`will_renew` is never an input.** Google's `CANCELED` and Apple's
       `AUTO_RENEW_DISABLED` mean *won't renew*, NOT *access ended*. Treating a
       cancellation as an immediate revocation is the single most common
       revenue-losing bug in subscriptions — the customer paid through the
       period and we would be cutting them off early. Grep this module for
       `will_renew`: it appears nowhere below.
    2. **Status is checked BEFORE dates**, so a refund revokes immediately even
       though Apple's REFUND can arrive with the original expiry intact.
    3. **Grace entitles, retry does not** (see ENTITLING_STATUSES).
    4. **Environment is re-checked here**, not only at the webhook, so a row
       written by an older or buggy build can never entitle in production. The
       failure it prevents — a tester's sandbox purchase granting a real
       Family plan — is silent and reproducible at will by anyone with a
       TestFlight build.
    """
    if sub.deleted_at is not None:
        return False
    if sub.environment != expected_environment:
        return False
    if sub.status not in ENTITLING_STATUSES:
        return False
    end = access_end(sub)
    if end is None:
        # No known expiry: entitle only while explicitly active. Conservative
        # on purpose — a malformed payload that dropped the expiry must not
        # grant forever.
        return sub.status == "active"
    return end > now


def tier_from_subscriptions(
    subs: list[Subscription],
    now: datetime.datetime,
    expected_environment: str = "production",
) -> str:
    """The tier these subscriptions grant, or free.

    Takes the MAX rather than the most recent. Max is order-independent, and
    webhooks arrive out of order by construction — so even if every ordering
    guard failed, recomputing from the same rows gives the same answer. That
    property is what makes the whole pipeline safe to replay.
    """
    tier = FREE
    for sub in subs:
        if is_entitling(sub, now, expected_environment):
            tier = higher_tier(tier, sub.tier)
    return tier


def tier_for_product(product_id: str, entitlement_id: str | None) -> str:
    """Map a store product to a Mamaflow tier.

    Matches on the tier name appearing in the entitlement or product id, so
    `mamaflow_pro_monthly`, `pro_annual` and an entitlement literally named
    `pro` all resolve without a hardcoded SKU table that would drift from the
    store catalogue.

    **An unmappable product on a live subscription grants `pro`, not `free`.**
    That deliberately departs from the house fail-closed stance
    (`entitlements.py`): that rule protects us from a stale row, but here the
    customer has demonstrably paid, and charging someone while serving them
    `free` is the worse failure. The ERROR log is the alarm — it is the only
    thing that makes a catalogue mistake visible.
    """
    haystack = f"{entitlement_id or ''} {product_id or ''}".lower()
    # Most generous match wins, so "family" is not shadowed by a product id
    # that also contains "pro" (e.g. "mamaflow_pro_family").
    for tier in reversed(TIERS):
        if tier != FREE and tier in haystack:
            return tier
    _log.error(
        "billing: no tier mapping for product %r entitlement %r — granting %s "
        "so a paying customer is not served free; fix the catalogue mapping",
        product_id,
        entitlement_id,
        PRO,
    )
    return PRO


async def active_subscriptions(db: AsyncSession, user_id) -> list[Subscription]:
    rows = await db.execute(
        select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.deleted_at.is_(None),
        )
    )
    return list(rows.scalars())


async def recompute_tier(
    db: AsyncSession,
    user: User,
    now: datetime.datetime | None = None,
    expected_environment: str = "production",
) -> str:
    """Set `users.tier` from this user's subscriptions and return it.

    Pure derivation: no entitling rows means `free` — the string, never NULL
    and never "leave whatever was there". The override is applied at READ time
    (`households.plan_tier`), not here, so a store event can never silently
    revert a deliberate grant.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    subs = await active_subscriptions(db, user.id)
    tier = tier_from_subscriptions(subs, now, expected_environment)
    if user.tier != tier:
        user.tier = tier
        await db.commit()
    return tier


def effective_tier(
    user: User, now: datetime.datetime | None = None
) -> str:
    """The tier this user actually gets: an unexpired override, else the
    projection.

    An override with a NULL expiry never lapses — that is the pre-launch
    testing mode, where a 30-day clock would run out mid-test. Support grants
    should set an expiry instead, because an override left on a real customer
    means their genuine cancellation never takes effect.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    override = user.tier_override
    if override:
        expires = _aware(user.tier_override_expires_at)
        if expires is None or expires > now:
            return entitlements_for(override).tier
    return entitlements_for(user.tier).tier


def clear_override(user: User) -> None:
    user.tier_override = None
    user.tier_override_expires_at = None
    user.tier_override_reason = None


def reset_billing_state(user: User) -> None:
    """Return a user to the free baseline — used on account deletion.

    Deliberately does NOT touch their `subscriptions` rows: the store is still
    charging them, and that row is the record we would need to answer a refund.
    """
    user.tier = DEFAULT_TIER
    clear_override(user)
