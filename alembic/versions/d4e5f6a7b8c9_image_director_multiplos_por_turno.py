"""image_director_multiplos_por_turno: permite vários relatórios por turno (v3.3)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a9b0
Create Date: 2026-09-01 18:35:00.000000

Remove índice único por turno — diretor pode lançar mais de um relatório
no mesmo turno/estúdio/data (ex.: turmas ou sessões distintas).
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _index_exists(table: str, index: str) -> bool:
    bind = op.get_bind()
    if table not in inspect(bind).get_table_names():
        return False
    return index in {idx["name"] for idx in inspect(bind).get_indexes(table)}


def upgrade() -> None:
    if _index_exists("image_director_reports", "uq_image_director_report_turno"):
        op.drop_index("uq_image_director_report_turno", table_name="image_director_reports")


def downgrade() -> None:
    if not _index_exists("image_director_reports", "uq_image_director_report_turno"):
        import sqlalchemy as sa

        op.create_index(
            "uq_image_director_report_turno",
            "image_director_reports",
            ["diretor_imagem_id", "data_relatorio", "turno", "estudio"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        )
