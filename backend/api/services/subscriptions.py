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


# --- applying a RevenueCat event ---------------------------------------------

# What each event type means for the subscription's status. Anything absent is
# recorded and ignored rather than guessed at (D34 coerce-don't-reject) — a new
# RevenueCat event type must never be interpreted as a revocation by accident.
_STATUS_BY_EVENT = {
    "INITIAL_PURCHASE": "active",
    "RENEWAL": "active",
    "PRODUCT_CHANGE": "active",
    "UNCANCELLATION": "active",
    "NON_RENEWING_PURCHASE": "active",
    "SUBSCRIPTION_EXTENDED": "active",
    "TRANSFER": "active",
    "CANCELLATION": None,  # "won't renew" — status deliberately unchanged
    "BILLING_ISSUE": "in_retry",
    "SUBSCRIPTION_PAUSED": "paused",
    "EXPIRATION": "expired",
}
KNOWN_EVENT_TYPES = frozenset(_STATUS_BY_EVENT) | {"SUBSCRIBER_ALIAS", "TEST"}

_STORE_BY_RC = {
    "APP_STORE": "app_store",
    "MAC_APP_STORE": "app_store",
    "PLAY_STORE": "play_store",
    "STRIPE": "stripe",
    "PROMOTIONAL": "promotional",
    "RC_BILLING": "rc_billing",
}


def _ms(value) -> datetime.datetime | None:
    if not isinstance(value, (int, float)):
        return None
    try:
        return datetime.datetime.fromtimestamp(value / 1000, tz=datetime.timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def status_for_event(event_type: str, cancel_reason: str | None) -> str | None:
    """The status this event implies, or None to leave it alone.

    `CANCELLATION` is the one that matters: it means the user turned off
    auto-renew, NOT that access ended — so it must not change the status. The
    exception is a refund, which RevenueCat also delivers as CANCELLATION but
    with a refund-ish reason.
    """
    if event_type == "CANCELLATION":
        if (cancel_reason or "").upper() in {"CUSTOMER_SUPPORT", "REFUND"}:
            return "refunded"
        return None
    return _STATUS_BY_EVENT.get(event_type)


async def apply_event(db: AsyncSession, event: dict, expected_environment: str):
    """Fold one RevenueCat event into `subscriptions` and return
    (outcome, subscription, user).

    Never raises on a malformed or unfamiliar event — those are recorded and
    ignored, because a permanently unprocessable event that 500s would be
    retried by RevenueCat forever and poison the delivery queue.
    """
    event_type = str(event.get("type") or "")
    environment = str(event.get("environment") or "PRODUCTION").upper()
    expected = "SANDBOX" if expected_environment == "sandbox" else "PRODUCTION"
    if environment != expected:
        # A sandbox purchase must never grant a real plan. Ignored, not
        # retried: it is a valid delivery we deliberately drop.
        return "ignored_sandbox", None, None
    if event_type not in KNOWN_EVENT_TYPES:
        return "ignored_unknown_type", None, None
    if event_type in {"SUBSCRIBER_ALIAS", "TEST"}:
        return "ignored_unknown_type", None, None

    app_user_id = str(event.get("app_user_id") or "").strip()
    store = _STORE_BY_RC.get(str(event.get("store") or "").upper(), "unknown")
    original_id = str(
        event.get("original_transaction_id")
        or event.get("transaction_id")
        or event.get("id")
        or ""
    ).strip()
    if not original_id:
        return "ignored_unknown_type", None, None

    event_at = _ms(event.get("event_timestamp_ms")) or datetime.datetime.now(
        datetime.timezone.utc
    )
    user = await _resolve_user(db, app_user_id, store, original_id)

    rows = await db.execute(
        select(Subscription).where(
            Subscription.store == store,
            Subscription.store_original_id == original_id,
        )
    )
    sub = rows.scalar_one_or_none()

    if sub is not None and sub.last_event_at is not None:
        if event_at <= _aware(sub.last_event_at):
            # Out of order. Ignore rather than apply — a later event has
            # already been folded in, and re-applying an older one would undo
            # it. Recorded so a redelivery does not repeat the no-op forever.
            return "ignored_stale", sub, user

    product_id = str(event.get("product_id") or "")
    entitlement_id = str(
        event.get("entitlement_id")
        or (event.get("entitlement_ids") or [None])[0]
        or ""
    ) or None
    cancel_reason = event.get("cancel_reason")
    new_status = status_for_event(event_type, cancel_reason)

    if sub is None:
        sub = Subscription(
            app_user_id=app_user_id,
            store=store,
            store_original_id=original_id,
            product_id=product_id,
            entitlement_id=entitlement_id,
            tier=tier_for_product(product_id, entitlement_id),
            status=new_status or "active",
        )
        db.add(sub)
    else:
        if product_id:
            sub.product_id = product_id
            sub.entitlement_id = entitlement_id
            sub.tier = tier_for_product(product_id, entitlement_id)
        if new_status is not None:
            sub.status = new_status

    sub.user_id = user.id if user is not None else sub.user_id
    if app_user_id:
        sub.app_user_id = app_user_id
    sub.last_event_type = event_type
    sub.last_event_at = event_at
    if (period_end := _ms(event.get("expiration_at_ms"))) is not None:
        sub.current_period_end = period_end
    if (grace := _ms(event.get("grace_period_expiration_at_ms"))) is not None:
        sub.grace_period_end = grace
    if period_type := event.get("period_type"):
        sub.period_type = str(period_type).lower()
    sub.environment = expected_environment

    if event_type == "CANCELLATION":
        sub.will_renew = False
        sub.unsubscribe_detected_at = event_at
    elif event_type in {"UNCANCELLATION", "RENEWAL", "INITIAL_PURCHASE"}:
        sub.will_renew = True
    if event_type == "BILLING_ISSUE":
        sub.billing_issue_detected_at = event_at
    if sub.status == "refunded":
        sub.refunded_at = event_at
        # Do not trust the store to have moved the expiry — Apple's refund can
        # arrive with it intact. Clamp it so nothing downstream can read the
        # row as still paid.
        end = _aware(sub.current_period_end)
        sub.current_period_end = min(end, event_at) if end else event_at

    await db.commit()
    if user is not None:
        await recompute_tier(db, user, expected_environment=expected_environment)
    return ("applied" if user is not None else "unresolved_user"), sub, user


async def _resolve_user(db: AsyncSession, app_user_id: str, store: str, original_id: str):
    """Map RevenueCat's app_user_id to our user.

    Orphans are expected, not exceptional: RevenueCat mints `$RCAnonymousID:…`
    before login, so a purchase made on the paywall before sign-in has no user
    yet. Falling back to the existing row's owner is what makes such a purchase
    resolve on its first RENEWAL even if the app never called the link endpoint.
    """
    import uuid as _uuid

    if app_user_id:
        try:
            user_id = _uuid.UUID(app_user_id)
        except (ValueError, AttributeError, TypeError):
            user_id = None
        if user_id is not None:
            # Soft-deleted users are accepted deliberately: the row exists and
            # the store is still charging them. Writing a tier there is inert
            # (a deleted user is 401'd), and it keeps tier == f(subscriptions)
            # true unconditionally, which is what lets reactivation just derive.
            user = await db.get(User, user_id)
            if user is not None:
                return user
    rows = await db.execute(
        select(Subscription).where(
            Subscription.store == store,
            Subscription.store_original_id == original_id,
            Subscription.user_id.is_not(None),
        )
    )
    existing = rows.scalar_one_or_none()
    if existing is not None:
        return await db.get(User, existing.user_id)
    return None


async def sweep_lapsed(
    session_factory,
    *,
    now: datetime.datetime | None = None,
    expected_environment: str = "production",
) -> int:
    """Downgrade users whose access has quietly run out. Returns how many moved.

    Exists because a webhook can be lost. RevenueCat retries for ~72h and then
    gives up, so a dropped EXPIRATION would otherwise entitle a lapsed
    subscription **forever** — nothing else in the system ever looks at that row
    again.

    Deliberately hourly rather than on every read: recomputing inside
    `/account/me` would add a query per request and make the tier a function of
    read traffic, so a dormant user would never downgrade at all. The cost is up
    to an hour of over-entitlement, which is the correct direction to be wrong —
    a paying parent locked out of their calendar is far worse than a lapsed one
    getting an extra hour.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    moved = 0
    async with session_factory() as db:
        # Only users holding a row that has actually lapsed. The index on
        # current_period_end is what keeps this off a table scan.
        rows = await db.execute(
            select(Subscription.user_id)
            .where(
                Subscription.user_id.is_not(None),
                Subscription.deleted_at.is_(None),
                Subscription.current_period_end.is_not(None),
                Subscription.current_period_end <= now,
            )
            .distinct()
        )
        user_ids = [r[0] for r in rows]
        for user_id in user_ids:
            user = await db.get(User, user_id)
            if user is None:
                continue
            before = user.tier
            after = await recompute_tier(
                db, user, now, expected_environment=expected_environment
            )
            if before != after:
                moved += 1
    if moved:
        # Counts only — never who or what they bought.
        _log.info("billing sweep: %d user(s) changed tier", moved)
    return moved
