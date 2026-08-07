"""Server-to-server webhooks (D47).

**Every route in this file is authenticated by a shared secret and by nothing
else.** It lives outside `routers/account.py` on purpose: every route there
carries `Depends(get_current_user)`, so an intentionally JWT-less route must
not sit where a missing dependency reads as normal.

Status codes are chosen for RevenueCat's retry behaviour, not for tidiness:
**2xx means "we have durably decided about this event"** — applied, duplicate,
sandbox, unknown type, unresolved user, stale. Only a genuinely transient
failure may be non-2xx, or a permanently unprocessable event is retried forever
and poisons the delivery queue.

There is deliberately **no `except Exception: return 200`**. That shape silently
drops paid upgrades while leaving every happy-path test green, so a DB failure
returns 500 and RevenueCat retries.
"""

import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.config.settings import settings
from api.db.session import get_db
from api.models.subscription import ProcessedStoreEvent
from api.services import auth_throttle
from api.services.subscriptions import apply_event

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


def _expected_environment() -> str:
    """Which store environment this deployment accepts.

    Production takes only real purchases; anywhere else takes only sandbox, so
    a real event pointed at staging cannot create a real-looking row.
    """
    return "production" if settings.environment == "production" else "sandbox"


async def _require_secret(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    """Shared-secret auth.

    Compared against the WHOLE header value with `hmac.compare_digest` — no
    `Bearer ` stripping, because a parsing branch in front of a secret
    comparison is a bug surface, and RevenueCat lets you configure the literal
    value including any prefix you want.

    Note honestly: this authenticates RevenueCat, not the store. Anyone holding
    the secret can forge any event, so it is TLS-only, >=32 chars, and rotating
    it is a runbook — not something to discover during an incident.
    """
    configured = settings.revenuecat_webhook_secret
    if not configured:
        # Never "accept anything when unconfigured" — that is exactly how a
        # staging URL becomes a tier-granting oracle.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing webhook is not configured.",
        )
    client_ip = request.client.host if request.client else "unknown"
    allowed, retry_after = auth_throttle.check(client_ip, "revenuecat-webhook")
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts.",
            headers={"Retry-After": str(retry_after)},
        )
    if not authorization or not hmac.compare_digest(authorization, configured):
        auth_throttle.record_failure(client_ip, "revenuecat-webhook")
        _log.warning("billing webhook: bad secret")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        )
    auth_throttle.record_success("revenuecat-webhook")


@router.post("/revenuecat", dependencies=[Depends(_require_secret)])
async def revenuecat_webhook(
    payload: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fold a RevenueCat event into the subscription state.

    Claims the event id BEFORE applying it. A crash between the two means the
    event is never applied — which is safe here because every RevenueCat event
    carries the subscriber's full current state rather than a delta, so the
    next event re-establishes the truth and the sweeper catches a lost expiry.
    The alternative (apply, then mark) re-applies on redelivery, which is
    harmless today but stops being so the moment anything here has a side
    effect. The two are deliberately not one transaction; don't "fix" that.
    """
    event = payload.get("event")
    if not isinstance(event, dict):
        _log.warning("billing webhook: payload has no event object")
        return {"status": "ignored_malformed"}
    event_id = str(event.get("id") or "").strip()
    if not event_id:
        _log.warning("billing webhook: event has no id")
        return {"status": "ignored_malformed"}

    expected_env = _expected_environment()
    marker = ProcessedStoreEvent(
        event_id=event_id,
        event_type=str(event.get("type") or "unknown"),
        app_user_id=str(event.get("app_user_id") or ""),
        store=str(event.get("store") or "") or None,
        environment=str(event.get("environment") or "").upper() or "UNKNOWN",
        outcome="pending",
    )
    db.add(marker)
    try:
        await db.commit()
    except IntegrityError:
        # Already handled. RevenueCat retries at-least-once, so this is the
        # normal path for a redelivery, not an error.
        await db.rollback()
        return {"status": "duplicate"}

    outcome, sub, user = await apply_event(db, event, expected_env)
    marker.outcome = outcome
    if sub is not None:
        marker.subscription_id = sub.id
    await db.commit()

    _log.info(
        "billing webhook: type=%s outcome=%s store=%s env=%s user=%s sub=%s",
        marker.event_type,
        outcome,
        marker.store,
        marker.environment,
        user.id if user is not None else None,
        sub.id if sub is not None else None,
    )
    if outcome == "unresolved_user":
        # Its own line: support needs the id to reconcile, and it is either our
        # uuid or an opaque RevenueCat anonymous id — not PII.
        _log.warning(
            "billing webhook: no user for app_user_id %r (event %s)",
            marker.app_user_id,
            marker.event_type,
        )
    return {"status": outcome}
