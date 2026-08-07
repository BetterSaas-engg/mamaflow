import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base, TimestampMixin


class Subscription(TimestampMixin, Base):
    """One store subscription, as reported by RevenueCat (D47).

    This table is the store's fact; `users.tier` is a projection of it
    (`services/subscriptions.py`). Keeping them separate is what makes the
    pipeline safe to replay: recomputing from the same rows always gives the
    same tier, so an out-of-order or duplicated webhook cannot corrupt state.

    Deliberately NOT stored: the raw webhook payload (its `subscriber_attributes`
    is arbitrary app-set data and the likeliest accidental-PII vector), any
    payment instrument, price/tax/commission (RevenueCat is the revenue system
    of record and does it better), email, country, and the signed receipt — a
    bearer credential, so D4 territory.
    """

    __tablename__ = "subscriptions"
    __table_args__ = (
        # The store's own notion of "this subscription": Apple's
        # original_transaction_id and Google's purchase_token are each stable
        # across every renewal. Making it unique means a double-applied event
        # writes the same row with the same values — idempotent at the STATE
        # level even if event-level dedupe loses a race.
        #
        # Deliberately NOT partial on deleted_at (unlike
        # uq_mail_connections_email_live): a re-purchase must land on the same
        # row and revive it, or "did this person ever pay?" has two answers.
        UniqueConstraint(
            "store", "store_original_id", name="uq_subscriptions_store_original"
        ),
        Index("ix_subscriptions_user_id", "user_id"),
        Index("ix_subscriptions_app_user_id", "app_user_id"),
        # The sweeper queries this to find lapsed rows; without it that job
        # table-scans every tick.
        Index("ix_subscriptions_period_end", "current_period_end"),
    )

    # NULLABLE on purpose. RevenueCat mints `$RCAnonymousID:…` before login, so
    # a purchase made on the paywall before sign-in arrives with no user to
    # attach to. The orphan row IS the durable fix — /account/billing/link
    # claims it later.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # RevenueCat's app_user_id as delivered. Normally our users.id as a string.
    app_user_id: Mapped[str] = mapped_column(nullable=False)

    # 'app_store' | 'play_store' | 'stripe' | 'promotional' | 'rc_billing'.
    # No DB CHECK — the set grows with the stores (D34/D38 precedent).
    store: Mapped[str] = mapped_column(nullable=False)
    store_original_id: Mapped[str] = mapped_column(nullable=False)
    product_id: Mapped[str] = mapped_column(nullable=False)
    entitlement_id: Mapped[str | None] = mapped_column(nullable=True)

    # The Mamaflow tier this product grants, resolved at write time.
    tier: Mapped[str] = mapped_column(nullable=False)

    # 'active' | 'in_grace' | 'in_retry' | 'paused' | 'expired' | 'refunded'
    # | 'revoked' | 'unknown'.
    status: Mapped[str] = mapped_column(nullable=False)
    # Recorded for support, and NEVER read by the entitling predicate — see
    # services/subscriptions.py. "Won't renew" is not "access ended".
    will_renew: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    current_period_end: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    grace_period_end: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 'normal' | 'trial' | 'intro' | 'promotional'. A trial entitles.
    period_type: Mapped[str] = mapped_column(
        nullable=False, default="normal", server_default="normal"
    )
    # 'production' | 'sandbox'. Checked in the predicate as well as at the
    # webhook, so a row written by an older buggy build can never entitle.
    environment: Mapped[str] = mapped_column(
        nullable=False, default="production", server_default="production"
    )

    last_event_type: Mapped[str | None] = mapped_column(nullable=True)
    # The monotonic guard: an event older than this is ignored.
    last_event_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    refunded_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    unsubscribe_detected_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    billing_issue_detected_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ProcessedStoreEvent(TimestampMixin, Base):
    """Every webhook event we have durably decided about.

    Exists for idempotency — RevenueCat retries, and Pub/Sub-style delivery is
    at-least-once — and so that "why did nothing happen for this customer" is
    answerable from typed columns instead of logged payloads.
    """

    __tablename__ = "processed_store_events"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_processed_store_events_event_id"),
    )

    event_id: Mapped[str] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(nullable=False)
    # Kept so an orphan can be traced without retaining a body. It is either
    # our own uuid or an opaque RevenueCat anonymous id — not PII.
    app_user_id: Mapped[str] = mapped_column(nullable=False)
    store: Mapped[str | None] = mapped_column(nullable=True)
    environment: Mapped[str] = mapped_column(nullable=False)
    event_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # 'applied' | 'ignored_stale' | 'ignored_sandbox' | 'ignored_unknown_type'
    # | 'unresolved_user' | 'pending'
    outcome: Mapped[str] = mapped_column(nullable=False)
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subscriptions.id"), nullable=True
    )
