"""create devices table

Revision ID: c3d2e1f0a9b8
Revises: b2c1d0e9f8a7
Create Date: 2026-06-23

Hand-written (autogenerate needs the live DB at head). Device + FCM token for
push (D22); de-duped by a unique fcm_token.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d2e1f0a9b8'
down_revision: Union[str, Sequence[str], None] = 'b2c1d0e9f8a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'devices',
        sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('fcm_token', sa.String(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_devices_user_id'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("platform IN ('ios', 'android')", name='ck_devices_platform'),
    )
    op.create_index(op.f('ix_devices_user_id'), 'devices', ['user_id'], unique=False)
    op.create_index(op.f('ix_devices_fcm_token'), 'devices', ['fcm_token'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_devices_fcm_token'), table_name='devices')
    op.drop_index(op.f('ix_devices_user_id'), table_name='devices')
    op.drop_table('devices')
