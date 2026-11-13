"""Integração Vimeo Sync: índice em nome_ficheiro_gerado (casamento por nomenclatura)

Revision ID: b2d4e6f8a0c1
Revises: a7f1c2e9d4b0
Create Date: 2026-06-23 12:00:00.000000

A cada chamada de POST /api/v1/external/vimeo-link o Assistente consulta
class_reports por nomenclatura (case-insensitive). Índice funcional em
lower(nome_ficheiro_gerado) acelera o casamento exato.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'b2d4e6f8a0c1'
down_revision = 'a7f1c2e9d4b0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_class_reports_nome_ficheiro_gerado "
        "ON class_reports (lower(nome_ficheiro_gerado))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_class_reports_nome_ficheiro_gerado")
