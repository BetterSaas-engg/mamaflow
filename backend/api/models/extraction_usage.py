import datetime
import uuid

from sqlalchemy import BigInteger, Date, ForeignKey, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base, TimestampMixin


class ExtractionUsageDaily(Base, TimestampMixin):
    """Per-user, per-day Claude extraction usage — durable cost accounting.

    Two jobs:
      1. A baseline. Extraction spend was previously invisible (message.usage
         was discarded), so a cost regression could only be discovered on the
         bill, days late.
      2. The substrate for the daily call budget, which structurally caps the
         blast radius of ANY future runaway — including ones nobody predicted.

    Counts only — no content, no per-message rows (D5 / audit rule).
    """

    __tablename__ = "extraction_usage"
    __table_args__ = (
        UniqueConstraint("user_id", "usage_date", name="uq_extraction_usage_user_date"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    # Date in UTC — a budget window only needs to be stable, not local.
    usage_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    calls: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default=text("0")
    )
    input_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    output_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
