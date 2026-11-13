"""fix_diretores_imagem_user_id: coluna faltante após stamp parcial

Revision ID: f7a8b9c0d1e2
Revises: e4f6a8b0c2d3
Create Date: 2026-09-01 11:00:00.000000

Produção: c9f1 foi marcada (stamp) sem executar o ADD COLUMN em diretores_imagem.user_id.
Isso quebra GET /api/v1/reports/ ao carregar diretor_imagem_nome.

Operação segura — apenas ADD COLUMN nullable + unique constraint.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "e4f6a8b0c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def _constraint_exists(table: str, constraint: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return constraint in {uc["name"] for uc in inspector.get_unique_constraints(table)}


def upgrade() -> None:
    if not _column_exists("diretores_imagem", "user_id"):
        op.add_column(
            "diretores_imagem",
            sa.Column(
                "user_id",
                PG_UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
        )
    if not _constraint_exists("diretores_imagem", "uq_diretores_imagem_user_id"):
        op.create_unique_constraint(
            "uq_diretores_imagem_user_id",
            "diretores_imagem",
            ["user_id"],
        )


def downgrade() -> None:
    if _constraint_exists("diretores_imagem", "uq_diretores_imagem_user_id"):
        op.drop_constraint(
            "uq_diretores_imagem_user_id", "diretores_imagem", type_="unique"
        )
    if _column_exists("diretores_imagem", "user_id"):
        op.drop_column("diretores_imagem", "user_id")
