import uuid

from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base, TimestampMixin


class SenderAllowlist(TimestampMixin, Base):
    __tablename__ = "sender_allowlist"

    user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    domain: Mapped[str] = mapped_column(nullable=False)
    sender_email: Mapped[str | None] = mapped_column(nullable=True)
    label: Mapped[str | None] = mapped_column(nullable=True)
