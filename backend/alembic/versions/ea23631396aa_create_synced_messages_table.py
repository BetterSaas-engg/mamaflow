"""create synced_messages table

Revision ID: ea23631396aa
Revises: d4e3f2a1b0c9
Create Date: 2026-07-23 20:26:16.432538

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ea23631396aa'
down_revision: Union[str, Sequence[str], None] = 'd4e3f2a1b0c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Only creates synced_messages. Autogenerate also proposed dropping
    # ix_sender_allowlist_domain / ix_sender_blocklist_domain — a false diff
    # (those indexes are real and in use); those drops were removed by hand.
    op.create_table('synced_messages',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('source_message_id', sa.String(), nullable=False),
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'source_message_id', name='uq_synced_messages_user_message')
    )
    op.create_index(op.f('ix_synced_messages_user_id'), 'synced_messages', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_synced_messages_user_id'), table_name='synced_messages')
    op.drop_table('synced_messages')
