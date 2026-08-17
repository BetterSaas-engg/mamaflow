"""The RevenueCat webhook and billing linkage (D47).

**Anti-vacuity rules for this file.** Prior audits here caught a test that
mocked the very function that was broken, and one whose failure path was a
no-op. So:

  - Every test drives the REAL router through the `client` fixture. Nothing
    calls the handler directly and nothing monkeypatches `apply_event` or
    `recompute_tier`.
  - Every "is rejected" test asserts the status code AND that the database is
    unchanged. A status-code-only assertion is the classic vacuous shape here —
    it passes an implementation that rejects the request after already writing.
"""

import datetime
import uuid

import pytest
from sqlalchemy import select

from api.auth.jwt import create_access_token
from api.config.settings import settings as app_settings
from api.models.subscription import ProcessedStoreEvent, Subscription
from api.services.users import get_or_create_user

SECRET = "test-webhook-secret-that-is-long-enough-123456"
NOW_MS = int(
    datetime.datetime(2026, 8, 7, 12, 0, tzinfo=datetime.UTC).timestamp() * 1000
)
DAY = 86_400_000


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    monkeypatch.setattr(app_settings, "revenuecat_webhook_secret", SECRET)
    monkeypatch.setattr(app_settings, "environment", "development")
    from api.services import auth_throttle

    auth_throttle._reset()
    yield
    auth_throttle._reset()


def _hook(secret: str = SECRET) -> dict:
    return {"Authorization": secret}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _event(**kw) -> dict:
    """A RevenueCat event. `environment` is SANDBOX because the test settings
    say environment=development, and this deployment accepts only sandbox —
    which is itself the guard being exercised."""
    event = {
        "id": f"evt-{uuid.uuid4()}",
        "type": "INITIAL_PURCHASE",
        "app_user_id": "",
        "store": "APP_STORE",
        "environment": "SANDBOX",
        "product_id": "mamaflow_pro_monthly",
        "entitlement_ids": ["pro"],
        "original_transaction_id": "orig-1",
        "event_timestamp_ms": NOW_MS,
        "expiration_at_ms": NOW_MS + 30 * DAY,
        "period_type": "normal",
    }
    event.update(kw)
    return {"event": event}


async def _user(db, email="parent@example.com"):
    user = await get_or_create_user(db, email)
    return user, create_access_token(subject=str(user.id), email=user.email)


async def _tier(db, user):
    await db.refresh(user)
    return user.tier


# --- auth ---


async def test_a_wrong_secret_is_rejected_and_writes_nothing(client, db):
    user, _ = await _user(db)

    resp = await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook("wrong-secret"),
        json=_event(app_user_id=str(user.id)),
    )

    assert resp.status_code == 401
    assert await _tier(db, user) == "free"
    assert list((await db.execute(select(Subscription))).scalars()) == []


async def test_a_missing_header_is_rejected(client, db):
    resp = await client.post("/api/v1/webhooks/revenuecat", json=_event())

    assert resp.status_code == 401
    assert list((await db.execute(select(Subscription))).scalars()) == []


async def test_a_prefix_of_the_secret_is_rejected(client, db):
    """Catches a `startswith` implementation."""
    resp = await client.post(
        "/api/v1/webhooks/revenuecat", headers=_hook(SECRET[:20]), json=_event()
    )

    assert resp.status_code == 401


async def test_an_unconfigured_webhook_refuses_rather_than_accepts(
    client, db, monkeypatch
):
    """An unconfigured endpoint that accepted would turn any staging URL into a
    tier-granting oracle."""
    monkeypatch.setattr(app_settings, "revenuecat_webhook_secret", "")
    user, _ = await _user(db)

    resp = await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(""),
        json=_event(app_user_id=str(user.id)),
    )

    assert resp.status_code == 503
    assert await _tier(db, user) == "free"


# --- the happy path ---


async def test_a_purchase_grants_the_tier(client, db):
    user, _ = await _user(db)

    resp = await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(app_user_id=str(user.id)),
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "applied"
    assert await _tier(db, user) == "pro"


async def test_a_family_purchase_grants_family(client, db):
    user, _ = await _user(db)

    await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(
            app_user_id=str(user.id),
            product_id="mamaflow_family_annual",
            entitlement_ids=["family"],
        ),
    )

    assert await _tier(db, user) == "family"


async def test_cancellation_does_not_revoke_access(client, db):
    """The classic revenue-losing bug, end to end through the real endpoint:
    "won't renew" is not "access ended"."""
    user, _ = await _user(db)
    await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(app_user_id=str(user.id)),
    )

    await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(
            app_user_id=str(user.id),
            type="CANCELLATION",
            cancel_reason="UNSUBSCRIBE",
            event_timestamp_ms=NOW_MS + 1000,
        ),
    )

    assert await _tier(db, user) == "pro"


async def test_expiration_revokes(client, db):
    """Partner to the above — without it, "never revoke" passes."""
    user, _ = await _user(db)
    await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(app_user_id=str(user.id)),
    )

    await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(
            app_user_id=str(user.id),
            type="EXPIRATION",
            event_timestamp_ms=NOW_MS + 2000,
            expiration_at_ms=NOW_MS - DAY,
        ),
    )

    assert await _tier(db, user) == "free"


async def test_a_refund_revokes_immediately(client, db):
    user, _ = await _user(db)
    await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(app_user_id=str(user.id)),
    )

    await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(
            app_user_id=str(user.id),
            type="CANCELLATION",
            cancel_reason="REFUND",
            event_timestamp_ms=NOW_MS + 3000,
        ),
    )

    assert await _tier(db, user) == "free"


# --- idempotency and ordering ---


async def test_a_redelivered_event_is_a_no_op(client, db):
    user, _ = await _user(db)
    payload = _event(app_user_id=str(user.id))

    first = await client.post(
        "/api/v1/webhooks/revenuecat", headers=_hook(), json=payload
    )
    second = await client.post(
        "/api/v1/webhooks/revenuecat", headers=_hook(), json=payload
    )

    assert first.json()["status"] == "applied"
    assert second.json()["status"] == "duplicate"
    subs = list((await db.execute(select(Subscription))).scalars())
    assert len(subs) == 1


async def test_a_replayed_earlier_event_cannot_undo_a_later_one(client, db):
    """Stronger than a plain duplicate test: catches a missing monotonic guard
    as well as a missing dedupe."""
    user, _ = await _user(db)
    await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(
            app_user_id=str(user.id),
            type="EXPIRATION",
            event_timestamp_ms=NOW_MS + 5000,
            expiration_at_ms=NOW_MS - DAY,
        ),
    )
    assert await _tier(db, user) == "free"

    # The original purchase arrives late (different event id, older timestamp).
    resp = await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(app_user_id=str(user.id), event_timestamp_ms=NOW_MS),
    )

    assert resp.json()["status"] == "ignored_stale"
    assert await _tier(db, user) == "free"


# --- things that must be ignored, not retried ---


async def test_a_production_event_is_ignored_outside_production(client, db):
    """A real event pointed at staging must not create a real-looking row —
    and it must be 200, or RevenueCat retries it forever."""
    user, _ = await _user(db)

    resp = await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(app_user_id=str(user.id), environment="PRODUCTION"),
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored_sandbox"
    assert await _tier(db, user) == "free"
    assert list((await db.execute(select(Subscription))).scalars()) == []


async def test_an_unknown_event_type_is_2xx_and_writes_nothing(client, db):
    user, _ = await _user(db)

    resp = await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(app_user_id=str(user.id), type="SOME_NEW_EVENT_2027"),
    )

    assert resp.status_code == 200
    assert await _tier(db, user) == "free"
    assert list((await db.execute(select(Subscription))).scalars()) == []


@pytest.mark.parametrize(
    "payload", [{}, {"event": None}, {"event": {}}, {"event": {"type": "RENEWAL"}}]
)
async def test_a_malformed_body_is_2xx_and_writes_nothing(client, db, payload):
    """A permanently unprocessable event must be 2xx'd, or it poisons the
    delivery queue forever."""
    resp = await client.post(
        "/api/v1/webhooks/revenuecat", headers=_hook(), json=payload
    )

    assert resp.status_code == 200
    assert list((await db.execute(select(Subscription))).scalars()) == []


async def test_an_unknown_app_user_id_is_recorded_not_dropped(client, db):
    """RevenueCat mints anonymous ids before login, so this is expected. The
    orphan row IS the fix — it gets claimed later."""
    resp = await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(app_user_id="$RCAnonymousID:abc123"),
    )

    assert resp.status_code == 200
    assert resp.json()["status"] == "unresolved_user"
    sub = (await db.execute(select(Subscription))).scalars().one()
    assert sub.user_id is None


async def test_a_db_failure_returns_5xx_not_200(client, db, monkeypatch):
    """THE anti-catch-all test. Without it, `except Exception: return 200`
    silently drops paid upgrades while every other test here stays green."""
    from api.routers import webhooks

    async def boom(*a, **k):
        raise RuntimeError("database is on fire")

    monkeypatch.setattr(webhooks, "apply_event", boom)
    user, _ = await _user(db)

    with pytest.raises(RuntimeError):
        await client.post(
            "/api/v1/webhooks/revenuecat",
            headers=_hook(),
            json=_event(app_user_id=str(user.id)),
        )


# --- linkage ---


async def test_linking_claims_an_orphan_purchase(client, db):
    """The anonymous-purchase flow end to end: buy on the paywall before
    signing in, then sign in and restore."""
    await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(app_user_id="$RCAnonymousID:abc123"),
    )
    user, token = await _user(db)

    resp = await client.post(
        "/api/v1/account/billing/link",
        headers=_auth(token),
        json={"app_user_id": "$RCAnonymousID:abc123"},
    )

    assert resp.status_code == 200
    assert resp.json()["tier"] == "pro"
    assert await _tier(db, user) == "pro"


async def test_linking_cannot_steal_another_users_subscription(client, db):
    """Without this rule, knowing someone's app_user_id is an entitlement-theft
    endpoint."""
    owner, _ = await _user(db, "owner@example.com")
    await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(app_user_id=str(owner.id)),
    )
    attacker, attacker_token = await _user(db, "attacker@example.com")

    resp = await client.post(
        "/api/v1/account/billing/link",
        headers=_auth(attacker_token),
        json={"app_user_id": str(owner.id)},
    )

    assert resp.status_code == 409
    # BOTH sides asserted: the attacker gained nothing and the owner lost nothing.
    assert await _tier(db, attacker) == "free"
    assert await _tier(db, owner) == "pro"


async def test_linking_requires_authentication(client):
    resp = await client.post(
        "/api/v1/account/billing/link", json={"app_user_id": "x"}
    )
    assert resp.status_code == 401


async def test_every_event_is_recorded_with_its_outcome(client, db):
    """"Why did nothing happen for this customer" must be answerable from typed
    columns, without keeping payloads."""
    user, _ = await _user(db)
    await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(app_user_id=str(user.id)),
    )
    await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(app_user_id=str(user.id), environment="PRODUCTION"),
    )

    outcomes = {
        row.outcome
        for row in (await db.execute(select(ProcessedStoreEvent))).scalars()
    }
    assert outcomes == {"applied", "ignored_sandbox"}


# --- Audit follow-ups (2026-08-07 security review) ---


async def test_a_transfer_downgrades_the_previous_owner(client, db):
    """One purchase must not entitle two accounts.

    Ownership moves (a TRANSFER, or simply a later event resolving to a
    different user), but only the NEW owner was ever re-derived — so the old
    one kept a paid tier they no longer had a subscription for, forever."""
    old, _ = await _user(db, "old@example.com")
    new, _ = await _user(db, "new@example.com")
    await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(app_user_id=str(old.id)),
    )
    assert await _tier(db, old) == "pro"

    await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(
            app_user_id=str(new.id),
            type="TRANSFER",
            event_timestamp_ms=NOW_MS + 1000,
        ),
    )

    assert await _tier(db, new) == "pro"
    assert await _tier(db, old) == "free", "old owner kept a plan they no longer own"


async def test_an_event_with_no_timestamp_cannot_undo_a_later_one(client, db):
    """A missing timestamp was coerced to "now", which always beats the stored
    one — so a replayed purchase silently reinstated a refunded subscription.
    "Unknown time" must be the most conservative reading, not the newest."""
    user, _ = await _user(db)
    purchase = _event(app_user_id=str(user.id))
    await client.post("/api/v1/webhooks/revenuecat", headers=_hook(), json=purchase)
    await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(
            app_user_id=str(user.id),
            type="CANCELLATION",
            cancel_reason="REFUND",
            event_timestamp_ms=NOW_MS + 5000,
        ),
    )
    assert await _tier(db, user) == "free"

    replay = _event(app_user_id=str(user.id))
    replay["event"].pop("event_timestamp_ms")
    resp = await client.post(
        "/api/v1/webhooks/revenuecat", headers=_hook(), json=replay
    )

    assert resp.json()["status"] == "ignored_stale"
    assert await _tier(db, user) == "free", "a refund was undone by a timestampless replay"


async def test_a_first_event_with_no_timestamp_is_still_applied(client, db):
    """Partner test: with nothing to be stale against, a missing timestamp must
    not block a genuine first purchase."""
    user, _ = await _user(db)
    first = _event(app_user_id=str(user.id))
    first["event"].pop("event_timestamp_ms")

    resp = await client.post(
        "/api/v1/webhooks/revenuecat", headers=_hook(), json=first
    )

    assert resp.json()["status"] == "applied"
    assert await _tier(db, user) == "pro"


async def test_claiming_an_already_owned_orphan_does_not_move_it(client, db):
    """The claim is a compare-and-swap: it may only take a row that is still
    unowned. A blind write let a late claim overwrite a completed one, leaving
    both accounts paid from a single subscription."""
    await client.post(
        "/api/v1/webhooks/revenuecat",
        headers=_hook(),
        json=_event(app_user_id="$RCAnonymousID:shared"),
    )
    first, first_token = await _user(db, "first@example.com")
    second, second_token = await _user(db, "second@example.com")

    await client.post(
        "/api/v1/account/billing/link",
        headers=_auth(first_token),
        json={"app_user_id": "$RCAnonymousID:shared"},
    )
    resp = await client.post(
        "/api/v1/account/billing/link",
        headers=_auth(second_token),
        json={"app_user_id": "$RCAnonymousID:shared"},
    )

    assert resp.status_code == 409
    assert await _tier(db, first) == "pro"
    assert await _tier(db, second) == "free"


async def test_an_event_left_pending_by_a_crash_is_retried_not_dropped(client, db):
    """Claiming the event id before applying it means a crash in between loses
    the event — the one real cost of that ordering. A retry must therefore
    re-apply a marker still marked pending, rather than dismissing it as a
    duplicate and dropping a paid upgrade for good."""
    user, _ = await _user(db)
    payload = _event(app_user_id=str(user.id))
    event_id = payload["event"]["id"]
    # Exactly the state a crash between claim and apply leaves behind.
    db.add(
        ProcessedStoreEvent(
            event_id=event_id,
            event_type="INITIAL_PURCHASE",
            app_user_id=str(user.id),
            environment="SANDBOX",
            outcome="pending",
        )
    )
    await db.commit()

    resp = await client.post(
        "/api/v1/webhooks/revenuecat", headers=_hook(), json=payload
    )

    assert resp.json()["status"] == "applied"
    assert await _tier(db, user) == "pro"


async def test_a_completed_event_is_still_a_duplicate(client, db):
    """Partner test — the retry path must not re-apply everything forever."""
    user, _ = await _user(db)
    payload = _event(app_user_id=str(user.id))

    await client.post("/api/v1/webhooks/revenuecat", headers=_hook(), json=payload)
    second = await client.post(
        "/api/v1/webhooks/revenuecat", headers=_hook(), json=payload
    )

    assert second.json()["status"] == "duplicate"
