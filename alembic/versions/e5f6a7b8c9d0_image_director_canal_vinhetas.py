"""image_director_canal_vinhetas: Canal IPTV por aula + obs vinhetas (v3.3)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-02 07:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    if table not in inspect(bind).get_table_names():
        return False
    return column in {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    if not _column_exists("image_director_lessons", "canal_utilizado"):
        op.add_column(
            "image_director_lessons",
            sa.Column("canal_utilizado", sa.String(50), nullable=True),
        )
    if not _column_exists("image_director_lessons", "vinhetas_corretas_obs"):
        op.add_column(
            "image_director_lessons",
            sa.Column("vinhetas_corretas_obs", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if _column_exists("image_director_lessons", "vinhetas_corretas_obs"):
        op.drop_column("image_director_lessons", "vinhetas_corretas_obs")
    if _column_exists("image_director_lessons", "canal_utilizado"):
        op.drop_column("image_director_lessons", "canal_utilizado")
