"""add users.provider

Revision ID: c57ffd09b56b
Revises: ea23631396aa
Create Date: 2026-07-26 11:17:17.776902

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c57ffd09b56b'
down_revision: Union[str, Sequence[str], None] = 'ea23631396aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add users.provider ('google' | 'yahoo' | 'icloud'; Phase 2 adds more).

    server_default='google' backfills every existing row correctly (all
    pre-existing users are Google). No DB CHECK on the value — the valid set
    is registry-validated in code and grows per provider (D34 precedent).
    Autogenerate's spurious sender_allowlist/blocklist index drops (a known
    false diff) were removed by hand.
    """
    op.add_column(
        "users",
        sa.Column("provider", sa.String(), server_default="google", nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "provider")
