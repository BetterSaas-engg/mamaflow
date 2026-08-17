"""create subscriptions + processed_store_events, add users tier override

Billing (D47). `users.tier` becomes a projection of `subscriptions`; the
override columns are a deliberate grant that outranks it — testers before the
app reaches the stores, support comps, and locking out a serial refunder.

Purely additive: every existing user keeps their current `tier` and gets NULL
overrides, i.e. exactly what they have today. No backfill.

Hand-written — autogenerate proposes dropping ix_sender_allowlist_domain /
ix_sender_blocklist_domain, a known false diff documented in ea23631396aa.

Revision ID: d5c81e9034af
Revises: e1a7b3c95d24
"""

import sqlalchemy as sa
from alembic import op

revision = "d5c81e9034af"
down_revision = "e1a7b3c95d24"
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
        "subscriptions",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Nullable: a purchase made before sign-in arrives under RevenueCat's
        # anonymous id with no user to attach to. The orphan row is the durable
        # fix — /account/billing/link claims it later.
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("app_user_id", sa.String(), nullable=False),
        sa.Column("store", sa.String(), nullable=False),
        sa.Column("store_original_id", sa.String(), nullable=False),
        sa.Column("product_id", sa.String(), nullable=False),
        sa.Column("entitlement_id", sa.String(), nullable=True),
        sa.Column("tier", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "will_renew",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grace_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "period_type", sa.String(), nullable=False, server_default="normal"
        ),
        sa.Column(
            "environment", sa.String(), nullable=False, server_default="production"
        ),
        sa.Column("last_event_type", sa.String(), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "unsubscribe_detected_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "billing_issue_detected_at", sa.DateTime(timezone=True), nullable=True
        ),
        *_timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        # The store's stable id for a subscription. NOT partial on deleted_at:
        # a re-purchase must land on the same row, or "did this person ever
        # pay?" has two answers.
        sa.UniqueConstraint(
            "store", "store_original_id", name="uq_subscriptions_store_original"
        ),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_app_user_id", "subscriptions", ["app_user_id"])
    # The sweeper finds lapsed rows through this; without it that job
    # table-scans every tick.
    op.create_index(
        "ix_subscriptions_period_end", "subscriptions", ["current_period_end"]
    )

    op.create_table(
        "processed_store_events",
        sa.Column(
            "id",
            sa.UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("app_user_id", sa.String(), nullable=False),
        sa.Column("store", sa.String(), nullable=True),
        sa.Column("environment", sa.String(), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("subscription_id", sa.UUID(), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", name="uq_processed_store_events_event_id"),
    )

    op.add_column("users", sa.Column("tier_override", sa.String(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "tier_override_expires_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "users", sa.Column("tier_override_reason", sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("users", "tier_override_reason")
    op.drop_column("users", "tier_override_expires_at")
    op.drop_column("users", "tier_override")
    op.drop_table("processed_store_events")
    op.drop_index("ix_subscriptions_period_end", table_name="subscriptions")
    op.drop_index("ix_subscriptions_app_user_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_user_id", table_name="subscriptions")
    op.drop_table("subscriptions")
