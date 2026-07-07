"""add users.last_reminder_date

Revision ID: d4e3f2a1b0c9
Revises: c3d2e1f0a9b8
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e3f2a1b0c9"
down_revision = "c3d2e1f0a9b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_reminder_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_reminder_date")
