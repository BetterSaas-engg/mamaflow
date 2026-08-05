import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base, TimestampMixin, _utcnow


class User(TimestampMixin, Base):
    __tablename__ = "users"

    # Email is the sign-in identity; stored lowercase, unique.
    email: Mapped[str] = mapped_column(unique=True, nullable=False, index=True)
    # Which mail provider this account syncs from: 'google' | 'yahoo' | 'icloud'
    # (Phase 2: 'microsoft'). Validated by the provider registry, not a DB
    # CHECK — the valid set grows per provider (D34 precedent).
    provider: Mapped[str] = mapped_column(
        nullable=False, default="google", server_default="google"
    )
    # Billing tier: 'free' | 'pro' | 'family' (D44). Drives the mailbox cap and
    # whether ads show. No DB CHECK — the valid set grows with pricing and is
    # validated in Python, where an unrecognised value degrades to free rather
    # than erroring (D34/D38 precedent). Limits live in services/entitlements.py,
    # never inline. There is no billing integration yet, so this is set
    # deliberately (admin/manual) and everyone defaults to free.
    tier: Mapped[str] = mapped_column(
        nullable=False, default="free", server_default="free"
    )
    # The household this user belongs to, if any (D46). NULL = solo account,
    # which is every user today. Membership is here rather than in a join table
    # because a user belongs to at most one household — the Family tier is two
    # parents, not an arbitrary graph.
    household_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("households.id"), nullable=True, index=True
    )
    # Last date (in REMINDER_TZ) a reminder digest was sent — daily dedup.
    last_reminder_date: Mapped[datetime.date | None] = mapped_column(nullable=True)
    # Last authenticated request from this user. Auto-sync skips accounts
    # dormant past AUTO_SYNC_DORMANT_DAYS, so someone who signs up once and
    # never returns stops costing Claude calls every hour forever. NOT NULL
    # with a now() default: a brand-new user must be eligible immediately, and
    # existing rows backfill to "seen at deploy" rather than "never seen".
    last_seen_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
