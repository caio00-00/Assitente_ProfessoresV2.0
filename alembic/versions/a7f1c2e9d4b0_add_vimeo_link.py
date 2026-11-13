"""Integração Vimeo Sync: adiciona coluna vimeo_link em class_reports

Revision ID: a7f1c2e9d4b0
Revises: 1e87efa00b86
Create Date: 2026-06-19 20:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7f1c2e9d4b0'
down_revision = '1e87efa00b86'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Link público do Vimeo da aula, preenchido via integração com o Vimeo Sync
    # (POST /api/v1/external/vimeo-link). Mantém video_link (Drive) intacto.
    op.add_column(
        'class_reports',
        sa.Column('vimeo_link', sa.String(length=1000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('class_reports', 'vimeo_link')
