"""extraction retry accounting and usage

Revision ID: 7b454f8c8a6d
Revises: c57ffd09b56b
Create Date: 2026-07-27 13:01:40.599840

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b454f8c8a6d'
down_revision: Union[str, Sequence[str], None] = 'c57ffd09b56b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Extraction cost control: per-message failure accounting + daily usage.

    `synced_messages` gains attempts/last_attempt_at/failure_kind so a
    permanently-failing message stops being re-sent to Claude every hour
    (previously ~720 full-price calls over a 30-day window — the dominant
    cost bug). Existing rows are all successes, so the defaults
    (attempts=0, failure_kind=NULL) are correct with no backfill.

    `extraction_usage` gives durable per-user/day cost accounting and backs
    the daily call budget. No CHECK on failure_kind — validated in Python
    (D34/D38 precedent). Autogenerate's sender_allowlist/blocklist index
    drops are the known false diff (see ea23631396aa) and were removed.
    """
    op.create_table('extraction_usage',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('usage_date', sa.Date(), nullable=False),
    sa.Column('calls', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('input_tokens', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('output_tokens', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'usage_date', name='uq_extraction_usage_user_date')
    )
    op.create_index(op.f('ix_extraction_usage_user_id'), 'extraction_usage', ['user_id'], unique=False)
    op.add_column('synced_messages', sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=False))
    op.add_column('synced_messages', sa.Column('last_attempt_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('synced_messages', sa.Column('failure_kind', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('synced_messages', 'failure_kind')
    op.drop_column('synced_messages', 'last_attempt_at')
    op.drop_column('synced_messages', 'attempts')
    op.drop_index(op.f('ix_extraction_usage_user_id'), table_name='extraction_usage')
    op.drop_table('extraction_usage')
