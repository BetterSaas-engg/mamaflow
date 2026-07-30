import datetime

from sqlalchemy import DateTime, text
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
