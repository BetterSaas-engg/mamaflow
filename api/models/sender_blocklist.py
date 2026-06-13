import uuid

from sqlalchemy import CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base, TimestampMixin


class SenderBlocklist(TimestampMixin, Base):
    __tablename__ = "sender_blocklist"
    __table_args__ = (
        CheckConstraint(
            "category IN ('financial', 'promotional')",
            name="ck_sender_blocklist_category",
        ),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    domain: Mapped[str | None] = mapped_column(nullable=True)
    pattern: Mapped[str | None] = mapped_column(nullable=True)
    category: Mapped[str] = mapped_column(nullable=False)
    reason: Mapped[str | None] = mapped_column(nullable=True)
