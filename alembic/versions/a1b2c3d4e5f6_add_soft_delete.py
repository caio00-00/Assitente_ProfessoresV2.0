"""add_soft_delete

Revision ID: a1b2c3d4e5f6
Revises: 8e7ea3a32e42
Create Date: 2026-04-20 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision = '8e7ea3a32e42'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('class_reports', 
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false')
    )

def downgrade() -> None:
    op.drop_column('class_reports', 'is_deleted')