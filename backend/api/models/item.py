import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base, TimestampMixin


class Item(TimestampMixin, Base):
    """A persisted extraction — an event (has a date) or a standalone action.

    One table for both, distinguished by item_type (decision: single items
    table). Raw email bodies are never stored (D5); only structured fields and
    the server-stamped source link/message id.
    """

    __tablename__ = "items"
    __table_args__ = (
        CheckConstraint(
            "item_type IN ('event', 'action')",
            name="ck_items_item_type",
        ),
        CheckConstraint(
            "status IN ('open', 'done', 'dismissed')",
            name="ck_items_status",
        ),
        Index("ix_items_user_message", "user_id", "source_message_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    item_type: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(nullable=False, default="open", server_default="open")

    event_title: Mapped[str | None] = mapped_column(nullable=True)
    action_required: Mapped[str | None] = mapped_column(nullable=True)
    event_date: Mapped[str | None] = mapped_column(nullable=True)
    event_time: Mapped[str | None] = mapped_column(nullable=True)
    location: Mapped[str | None] = mapped_column(nullable=True)
    child_name: Mapped[str | None] = mapped_column(nullable=True)
    event_type: Mapped[str | None] = mapped_column(nullable=True)
    source_sender: Mapped[str | None] = mapped_column(nullable=True)
    source_email_link: Mapped[str | None] = mapped_column(nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(nullable=True)
