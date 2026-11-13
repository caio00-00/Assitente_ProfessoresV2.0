"""external_api_setup: actor_id nullable + index bncc_habilidades

Revision ID: e1f2a3b4c5d6
Revises: a5beebd0c15b
Create Date: 2026-05-25 10:00:00.000000

Mudanças:
    1. audit_logs.actor_id → nullable (permite logs de acesso M2M sem usuário interno)
    2. Índice parcial em class_reports.bncc_habilidades (otimização de consultas externas)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "a5beebd0c15b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Aplica as mudanças necessárias para a API externa M2M."""

    # 1. Torna actor_id nullable para suportar chamadas externas sem usuário interno
    op.alter_column(
        "audit_logs",
        "actor_id",
        existing_type=PG_UUID(as_uuid=True),
        nullable=True,
    )

    # 2. Índice parcial em bncc_habilidades para otimizar buscas externas
    #    Usa cast para texto para suportar coluna JSON ou TEXT indistintamente
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_class_reports_habilidades
        ON class_reports ((bncc_habilidades::text))
        WHERE bncc_habilidades IS NOT NULL;
    """)


def downgrade() -> None:
    """Reverte as mudanças da API externa M2M."""

    # Remove o índice
    op.execute("DROP INDEX IF EXISTS idx_class_reports_habilidades;")

    # Restaura actor_id como NOT NULL (atenção: falha se existirem registros com NULL)
    op.alter_column(
        "audit_logs",
        "actor_id",
        existing_type=PG_UUID(as_uuid=True),
        nullable=False,
    )
