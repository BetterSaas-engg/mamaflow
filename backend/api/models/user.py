from sqlalchemy.orm import Mapped, mapped_column

from api.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    # Email is the identity from Google sign-in; stored lowercase, unique.
    email: Mapped[str] = mapped_column(unique=True, nullable=False, index=True)
