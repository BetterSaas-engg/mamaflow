"""create households + household_invites, add users.household_id

The Family tier (D44) is two parents sharing one plan and one calendar. This
adds the grouping that makes the second parent possible (D46).

Additive only: `users.household_id` is NULLABLE and every existing row stays
NULL, i.e. a solo account, which is exactly what they are today. No backfill,
and nothing changes for anyone until they create or join a household.

Invite codes are stored HASHED — a code is a bearer credential that grants
sight of a household's calendar, so a database read must not yield working
invitations.

Hand-written — autogenerate proposes dropping ix_sender_allowlist_domain /
ix_sender_blocklist_domain, a known false diff documented in ea23631396aa.

Revision ID: e1a7b3c95d24
Revises: c9f4a2b81e37
"""

import sqlalchemy as sa
from alembic import op

revision = "e1a7b3c95d24"
down_revision = "c9f4a2b81e37"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "households",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_households_owner_user_id", "households", ["owner_user_id"]
    )

    op.create_table(
        "household_invites",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("household_id", sa.UUID(), nullable=False),
        sa.Column("code_hash", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by_user_id", sa.UUID(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["household_id"], ["households.id"]),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_household_invites_household_id", "household_invites", ["household_id"]
    )
    op.create_index(
        "ix_household_invites_code_hash", "household_invites", ["code_hash"]
    )

    op.add_column(
        "users", sa.Column("household_id", sa.UUID(), nullable=True)
    )
    op.create_index("ix_users_household_id", "users", ["household_id"])
    op.create_foreign_key(
        "fk_users_household_id", "users", "households", ["household_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_household_id", "users", type_="foreignkey")
    op.drop_index("ix_users_household_id", table_name="users")
    op.drop_column("users", "household_id")
    op.drop_index("ix_household_invites_code_hash", table_name="household_invites")
    op.drop_index("ix_household_invites_household_id", table_name="household_invites")
    op.drop_table("household_invites")
    op.drop_index("ix_households_owner_user_id", table_name="households")
    op.drop_table("households")
