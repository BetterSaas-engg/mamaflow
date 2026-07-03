import uuid

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base, TimestampMixin


class Device(TimestampMixin, Base):
    """A user's device + FCM token for push (D22). De-duped by fcm_token."""

    __tablename__ = "devices"
    __table_args__ = (
        CheckConstraint("platform IN ('ios', 'android')", name="ck_devices_platform"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    fcm_token: Mapped[str] = mapped_column(nullable=False, unique=True, index=True)
    platform: Mapped[str] = mapped_column(nullable=False)
