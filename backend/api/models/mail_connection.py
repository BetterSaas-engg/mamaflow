import uuid

from sqlalchemy import ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base, TimestampMixin


class MailConnection(TimestampMixin, Base):
    """One mailbox a user has connected. A user may have several (D44 caps:
    free 1, pro 2, family 2 per parent).

    This is the multi-mailbox table deferred at D38, where Phase 1 deliberately
    kept exactly one mail source per user on `users.provider` and every sign-in
    PURGED the credentials of any other provider. That made a second mailbox
    impossible by construction, so the paid tiers had nothing to sell.

    `email` is the MAILBOX address, which is not necessarily the account's
    sign-in identity — the whole point of the table. It doubles as the
    credential-store key: tokens are keyed by (mailbox email, provider), so
    each connection already maps to its own secret with no key changes.

    Credentials themselves never live here (D4) — only the fact of the
    connection. Soft-deleted like all PII-bearing rows.
    """

    __tablename__ = "mail_connections"
    __table_args__ = (
        # A mailbox can only be connected once per user — but only among LIVE
        # rows, so disconnecting and reconnecting the same address works
        # instead of colliding with the tombstone.
        Index(
            "uq_mail_connections_user_email_live",
            "user_id",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    # 'google' | 'yahoo' | 'icloud' (Phase 2: 'microsoft'). Registry-validated,
    # no DB CHECK — D34/D38 precedent.
    provider: Mapped[str] = mapped_column(nullable=False)
    # Stored lowercase; the credential-store key and the address we read mail
    # from.
    email: Mapped[str] = mapped_column(nullable=False)
