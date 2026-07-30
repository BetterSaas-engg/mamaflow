"""add users.tier (billing tier: free | pro | family)

Drives the per-user mailbox cap and whether ads show (D44). No DB CHECK — the
valid set grows with pricing and is validated in Python, where an unrecognised
value degrades to free rather than erroring (D34/D38 precedent).

NOT NULL with server_default 'free': existing rows are all free users, so this
is correct by construction with no backfill. Hand-written — autogenerate
proposes dropping ix_sender_allowlist_domain / ix_sender_blocklist_domain, a
known false diff documented in ea23631396aa.

Revision ID: b2e7c419d5aa
Revises: a8f1c2d43e70
"""

import sqlalchemy as sa
from alembic import op

revision = "b2e7c419d5aa"
down_revision = "a8f1c2d43e70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "tier",
            sa.String(),
            nullable=False,
            server_default="free",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "tier")
