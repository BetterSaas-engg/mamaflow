"""create items table

Revision ID: b2c1d0e9f8a7
Revises: 105f5ff0fdeb
Create Date: 2026-06-23

Hand-written (autogenerate needs the live DB at head; the users migration is
not yet applied to the shared DB). Single table for events + actions.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c1d0e9f8a7'
down_revision: Union[str, Sequence[str], None] = '105f5ff0fdeb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'items',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('item_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), server_default='open', nullable=False),
        sa.Column('event_title', sa.String(), nullable=True),
        sa.Column('action_required', sa.String(), nullable=True),
        sa.Column('event_date', sa.String(), nullable=True),
        sa.Column('event_time', sa.String(), nullable=True),
        sa.Column('location', sa.String(), nullable=True),
        sa.Column('child_name', sa.String(), nullable=True),
        sa.Column('event_type', sa.String(), nullable=True),
        sa.Column('source_sender', sa.String(), nullable=True),
        sa.Column('source_email_link', sa.String(), nullable=True),
        sa.Column('source_message_id', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_items_user_id'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("item_type IN ('event', 'action')", name='ck_items_item_type'),
        sa.CheckConstraint("status IN ('open', 'done', 'dismissed')", name='ck_items_status'),
    )
    op.create_index(op.f('ix_items_user_id'), 'items', ['user_id'], unique=False)
    op.create_index('ix_items_user_message', 'items', ['user_id', 'source_message_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_items_user_message', table_name='items')
    op.drop_index(op.f('ix_items_user_id'), table_name='items')
    op.drop_table('items')
