import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base, TimestampMixin


class SyncedMessage(TimestampMixin, Base):
    """A per-(user, Gmail message) marker that the message was successfully
    processed by extraction — even when it produced zero events.

    Why it exists: incremental sync used to dedup on the `items` table alone,
    so an email that passed the blocklist but yielded no family events never
    left a trace and was re-fetched + re-sent to Claude on every hourly tick.
    A marker is written after a *successful* extraction regardless of event
    count, so zero-event mail is never re-extracted; a *failed* extraction
    writes no marker, preserving the intended next-sync retry.
    """

    __tablename__ = "synced_messages"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "source_message_id", name="uq_synced_messages_user_message"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    source_message_id: Mapped[str] = mapped_column(nullable=False)
