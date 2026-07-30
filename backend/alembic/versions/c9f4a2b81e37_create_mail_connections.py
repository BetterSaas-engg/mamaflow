"""create mail_connections (multi-mailbox) and backfill from users

The table deferred at D38. Phase 1 kept exactly one mail source per user on
`users.provider`, and every sign-in purged the credentials of any other
provider — so a second mailbox was impossible and the paid tiers (D44) had
nothing to sell.

THE BACKFILL IS LOAD-BEARING: sync reads mailboxes from this table, so every
existing user needs their current (email, provider) migrated across or their
mail silently stops syncing. Existing credentials are already keyed by
(mailbox email, provider) in the credential store, and for these rows the
mailbox email IS users.email, so the backfilled rows line up with the secrets
that already exist — no credential migration needed.

The unique index is PARTIAL (deleted_at IS NULL) so disconnecting and
reconnecting the same address works instead of colliding with the tombstone.

Hand-written — autogenerate proposes dropping ix_sender_allowlist_domain /
ix_sender_blocklist_domain, a known false diff documented in ea23631396aa.

Revision ID: c9f4a2b81e37
Revises: b2e7c419d5aa
"""

import sqlalchemy as sa
from alembic import op

revision = "c9f4a2b81e37"
down_revision = "b2e7c419d5aa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mail_connections",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mail_connections_user_id", "mail_connections", ["user_id"]
    )
    op.create_index(
        "uq_mail_connections_user_email_live",
        "mail_connections",
        ["user_id", "email"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    # Backfill: one connection per live user, from the Phase 1 columns.
    op.execute(
        """
        INSERT INTO mail_connections (user_id, provider, email)
        SELECT id, provider, email FROM users WHERE deleted_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index(
        "uq_mail_connections_user_email_live", table_name="mail_connections"
    )
    op.drop_index("ix_mail_connections_user_id", table_name="mail_connections")
    op.drop_table("mail_connections")
