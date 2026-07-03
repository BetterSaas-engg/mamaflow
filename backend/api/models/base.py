import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    # Both defaults are set: the Postgres server_default backs raw/migration
    # inserts, while the Python default keeps ORM inserts dialect-independent
    # (so the in-memory SQLite test DB, which lacks gen_random_uuid()/now(),
    # works too). ORM inserts use the Python default.
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=text("now()"),
    )
    # Client-side onupdate — works for all writes through SQLAlchemy.
    # Bulk raw-SQL updates won't trigger this; add a PG trigger if needed later.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=text("now()"),
        onupdate=_utcnow,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
