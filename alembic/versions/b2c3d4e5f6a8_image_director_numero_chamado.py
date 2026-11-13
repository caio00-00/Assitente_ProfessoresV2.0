"""image_director_numero_chamado: Nº chamado para aula gravada (v3.3)

Revision ID: b2c3d4e5f6a8
Revises: a1b2c3d4e5f7
Create Date: 2026-09-01 15:10:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "b2c3d4e5f6a8"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    if table not in inspect(bind).get_table_names():
        return False
    return column in {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    if not _column_exists("image_director_lessons", "numero_chamado"):
        op.add_column(
            "image_director_lessons",
            sa.Column("numero_chamado", sa.String(32), nullable=True),
        )


def downgrade() -> None:
    if _column_exists("image_director_lessons", "numero_chamado"):
        op.drop_column("image_director_lessons", "numero_chamado")
