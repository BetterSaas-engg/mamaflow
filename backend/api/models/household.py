import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base, TimestampMixin


class Household(TimestampMixin, Base):
    """Two parents sharing one plan and one family calendar (D44 Family tier).

    Deliberately thin: the tier lives on the OWNER's user row, and membership
    is `users.household_id`. Members keep their own logins, their own mailboxes
    and their own credentials — a household shares the plan and the calendar,
    never the mailbox access.
    """

    __tablename__ = "households"

    # Whose plan this is. Also the billing owner once billing exists, and the
    # only member who can invite or remove others.
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )


class HouseholdInvite(TimestampMixin, Base):
    """A pending invitation for a second parent to join.

    Accepted by CODE rather than by emailed link: there is no outbound email
    sender in the product yet, and inventing one just for this would be a much
    larger surface (deliverability, spoofing, unsubscribe) than the feature
    needs. The owner shares the code however they already talk to their
    partner.

    The code is stored HASHED. It is a bearer credential — anyone holding it
    can join the household and see its calendar — so a database read must not
    hand out working invitations (same reasoning as never storing raw tokens,
    D4).
    """

    __tablename__ = "household_invites"
    __table_args__ = (
        Index("ix_household_invites_code_hash", "code_hash"),
    )

    household_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("households.id"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(nullable=False)
    # Invitations expire so a code shared in a chat thread years ago can't be
    # redeemed by whoever scrolls back to it.
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def is_open(self) -> bool:
        return (
            self.accepted_at is None
            and self.revoked_at is None
            and self.deleted_at is None
        )
