"""`users.tier` as a projection of subscriptions (D47).

**Anti-vacuity rules for this file.** Prior audits here caught a test that
mocked the very function that was broken, and one whose "failure" path was a
no-op. So:

  - No test may monkeypatch `recompute_tier` or `is_entitling`. A test that
    wants a tier builds subscription rows.
  - Every "does not entitle" test has a partner "does entitle" test. Either
    alone admits a trivially wrong implementation (always-free / always-paid).
  - Assertions are on the resolved tier, not on intermediate booleans.
"""

import datetime

import pytest

from api.models.subscription import Subscription
from api.services.entitlements import FAMILY, FREE, PRO
from api.services.subscriptions import (
    effective_tier,
    recompute_tier,
    tier_for_product,
    tier_from_subscriptions,
)
from api.services.users import get_or_create_user

NOW = datetime.datetime(2026, 8, 6, 12, 0, tzinfo=datetime.UTC)
LATER = NOW + datetime.timedelta(days=10)
EARLIER = NOW - datetime.timedelta(days=10)


def _sub(**kw) -> Subscription:
    defaults = dict(
        app_user_id="u",
        store="app_store",
        store_original_id="orig-1",
        product_id="mamaflow_pro_monthly",
        entitlement_id="pro",
        tier=PRO,
        status="active",
        will_renew=True,
        current_period_end=LATER,
        period_type="normal",
        environment="production",
    )
    defaults.update(kw)
    return Subscription(**defaults)


# --- the entitling predicate: each pair kills a specific wrong implementation


def test_cancelled_but_unexpired_still_entitles():
    """THE most valuable test here. Google's CANCELED and Apple's
    AUTO_RENEW_DISABLED mean "won't renew", not "access ended" — the customer
    paid through the period. Revoking on cancellation is the classic
    revenue-losing bug."""
    sub = _sub(will_renew=False, unsubscribe_detected_at=NOW)

    assert tier_from_subscriptions([sub], NOW) == PRO


def test_an_expired_subscription_does_not_entitle():
    """Partner to the above — without it, "always entitle" passes."""
    sub = _sub(current_period_end=EARLIER, status="expired")

    assert tier_from_subscriptions([sub], NOW) == FREE


def test_grace_period_still_entitles():
    """Payment failed but the store is retrying and the user keeps access."""
    sub = _sub(
        status="in_grace",
        current_period_end=EARLIER,
        grace_period_end=LATER,
    )

    assert tier_from_subscriptions([sub], NOW) == PRO


def test_billing_retry_without_grace_does_not_entitle():
    """Partner to the above. Apple's retry runs up to 60 days UNENTITLED."""
    sub = _sub(status="in_retry", current_period_end=EARLIER)

    assert tier_from_subscriptions([sub], NOW) == FREE


def test_a_retrying_subscription_survives_so_a_late_renewal_re_grants():
    """The row must not be deleted on retry: a renewal arriving weeks later
    has to re-grant with no special case."""
    sub = _sub(status="in_retry", current_period_end=EARLIER)
    assert tier_from_subscriptions([sub], NOW) == FREE

    sub.status = "active"
    sub.current_period_end = LATER

    assert tier_from_subscriptions([sub], NOW) == PRO


def test_a_refund_revokes_even_with_a_future_period_end():
    """Status is checked BEFORE dates — Apple's REFUND can arrive with the
    original expiry intact."""
    sub = _sub(status="refunded", refunded_at=NOW, current_period_end=LATER)

    assert tier_from_subscriptions([sub], NOW) == FREE


def test_a_trial_entitles():
    sub = _sub(period_type="trial")

    assert tier_from_subscriptions([sub], NOW) == PRO


def test_sandbox_never_entitles_in_production():
    """A tester's sandbox purchase granting a real Family plan would be silent
    and reproducible at will by anyone with a TestFlight build."""
    sub = _sub(environment="sandbox", tier=FAMILY)

    assert tier_from_subscriptions([sub], NOW) == FREE
    # ...but does entitle when we ARE the sandbox.
    assert tier_from_subscriptions([sub], NOW, "sandbox") == FAMILY


def test_no_expiry_entitles_only_while_explicitly_active():
    """A malformed payload that dropped the expiry must not grant forever."""
    assert tier_from_subscriptions([_sub(current_period_end=None)], NOW) == PRO
    assert (
        tier_from_subscriptions(
            [_sub(current_period_end=None, status="expired")], NOW
        )
        == FREE
    )


def test_no_subscriptions_is_the_string_free():
    """Never NULL, never "leave what was there"."""
    assert tier_from_subscriptions([], NOW) == FREE


@pytest.mark.parametrize("order", [(0, 1), (1, 0)])
def test_overlapping_subscriptions_take_the_highest_tier(order):
    """Order-independence is the property that matters — webhooks arrive out of
    order by construction, so recomputing from the same rows must always give
    the same answer."""
    rows = [
        _sub(tier=PRO, store_original_id="a"),
        _sub(tier=FAMILY, store_original_id="b", entitlement_id="family"),
    ]
    ordered = [rows[order[0]], rows[order[1]]]

    assert tier_from_subscriptions(ordered, NOW) == FAMILY


def test_an_expired_family_does_not_drag_down_a_live_pro():
    rows = [
        _sub(tier=FAMILY, store_original_id="a", status="expired",
             current_period_end=EARLIER),
        _sub(tier=PRO, store_original_id="b"),
    ]

    assert tier_from_subscriptions(rows, NOW) == PRO


# --- product mapping


def test_products_map_to_their_tier():
    assert tier_for_product("mamaflow_pro_monthly", "pro") == PRO
    assert tier_for_product("mamaflow_family_annual", "family") == FAMILY
    assert tier_for_product("anything", "family") == FAMILY


def test_family_is_not_shadowed_by_a_product_id_containing_pro():
    assert tier_for_product("mamaflow_pro_family_bundle", None) == FAMILY


def test_an_unmappable_product_grants_the_lowest_paid_tier_and_shouts(caplog):
    """Deliberately NOT fail-closed. The customer has demonstrably paid, and
    charging someone while serving them free is the worse failure — so grant
    the lowest paid tier and make the catalogue mistake loud."""
    import logging

    with caplog.at_level(logging.ERROR):
        assert tier_for_product("some_new_sku", None) == PRO

    assert "no tier mapping" in caplog.text


# --- the override (the pre-launch testing mechanism)


async def test_an_override_beats_the_projection(db):
    user = await get_or_create_user(db, "tester@example.com")
    user.tier = FREE
    user.tier_override = FAMILY
    user.tier_override_reason = "beta tester"

    assert effective_tier(user, NOW) == FAMILY


async def test_an_override_with_no_expiry_never_lapses(db):
    """The pre-launch testing window: a 30-day clock would run out mid-test."""
    user = await get_or_create_user(db, "tester@example.com")
    user.tier_override = PRO
    user.tier_override_expires_at = None

    assert effective_tier(user, NOW + datetime.timedelta(days=3650)) == PRO


async def test_an_expired_override_stops_applying(db):
    """Support grants should expire — an override left on a real customer means
    their genuine cancellation never takes effect."""
    user = await get_or_create_user(db, "comped@example.com")
    user.tier = FREE
    user.tier_override = FAMILY
    user.tier_override_expires_at = EARLIER

    assert effective_tier(user, NOW) == FREE


async def test_an_unknown_override_value_degrades_to_free(db):
    user = await get_or_create_user(db, "typo@example.com")
    user.tier_override = "familly"

    assert effective_tier(user, NOW) == FREE


# --- recompute writes the projection


async def test_recompute_promotes_and_demotes(db):
    user = await get_or_create_user(db, "buyer@example.com")
    db.add(_sub(user_id=user.id, app_user_id=str(user.id)))
    await db.commit()

    assert await recompute_tier(db, user, NOW) == PRO

    from sqlalchemy import select

    rows = await db.execute(select(Subscription))
    rows.scalars().first().status = "expired"
    await db.commit()

    assert await recompute_tier(db, user, NOW) == FREE


async def test_recompute_does_not_touch_the_override(db):
    """A store event must never silently revert a deliberate grant — that is
    the entire reason the override lives in its own column."""
    user = await get_or_create_user(db, "tester@example.com")
    user.tier_override = FAMILY
    user.tier_override_reason = "beta"
    await db.commit()

    # No subscriptions at all: the projection says free...
    assert await recompute_tier(db, user, NOW) == FREE
    # ...but what the user actually gets is unchanged.
    assert effective_tier(user, NOW) == FAMILY


# --- the sweeper: the only thing that catches a LOST expiry event ---


async def test_the_sweeper_downgrades_a_lapsed_subscription(db, session_factory):
    """RevenueCat gives up retrying after ~72h. Without this, a dropped
    EXPIRATION entitles a lapsed subscription forever — nothing else in the
    system ever looks at that row again."""
    from api.services.subscriptions import sweep_lapsed

    user = await get_or_create_user(db, "lapsed@example.com")
    db.add(
        _sub(
            user_id=user.id,
            app_user_id=str(user.id),
            # Still marked active: the EXPIRATION webhook never arrived.
            status="active",
            current_period_end=EARLIER,
        )
    )
    user.tier = PRO
    await db.commit()

    moved = await sweep_lapsed(session_factory, now=NOW)

    await db.refresh(user)
    assert moved == 1
    assert user.tier == FREE


async def test_the_sweeper_leaves_active_and_grace_alone(db, session_factory):
    """Partner test — without it, "downgrade everyone" passes."""
    from api.services.subscriptions import sweep_lapsed

    active = await get_or_create_user(db, "active@example.com")
    grace = await get_or_create_user(db, "grace@example.com")
    db.add(_sub(user_id=active.id, app_user_id=str(active.id), store_original_id="a"))
    db.add(
        _sub(
            user_id=grace.id,
            app_user_id=str(grace.id),
            store_original_id="b",
            status="in_grace",
            current_period_end=EARLIER,
            grace_period_end=LATER,
        )
    )
    active.tier = PRO
    grace.tier = PRO
    await db.commit()

    moved = await sweep_lapsed(session_factory, now=NOW)

    await db.refresh(active)
    await db.refresh(grace)
    assert moved == 0
    assert active.tier == PRO
    assert grace.tier == PRO


async def test_the_sweeper_does_not_touch_an_override(db, session_factory):
    """A tester on a --forever grant must not be swept back to free."""
    from api.services.subscriptions import effective_tier, sweep_lapsed

    user = await get_or_create_user(db, "tester@example.com")
    user.tier_override = FAMILY
    user.tier_override_reason = "beta"
    await db.commit()

    await sweep_lapsed(session_factory, now=NOW)

    await db.refresh(user)
    assert effective_tier(user, NOW) == FAMILY


async def test_the_sweeper_reports_rows_it_structurally_cannot_lapse(
    db, session_factory, caplog
):
    """An active row with no expiry entitles indefinitely, and the sweep query
    filters on current_period_end so it can never see it. We sell only
    subscriptions, so in practice that means a payload mapping bug — report it
    rather than revoke, because cutting off a payer over a parsing bug is the
    worse error."""
    import logging

    from api.services.subscriptions import sweep_lapsed

    user = await get_or_create_user(db, "noexpiry@example.com")
    db.add(
        _sub(user_id=user.id, app_user_id=str(user.id), current_period_end=None)
    )
    await db.commit()

    with caplog.at_level(logging.WARNING):
        await sweep_lapsed(session_factory, now=NOW)

    assert "no expiry" in caplog.text
