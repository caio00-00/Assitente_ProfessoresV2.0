"""idr_contexto_operacional: professor, regular, avulsa no cabeçalho IDR

Revision ID: g9h0i1j2k3l4
Revises: f8a9b0c1d2e3
Create Date: 2026-09-04 04:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "g9h0i1j2k3l4"
down_revision: Union[str, Sequence[str], None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    if table not in inspect(bind).get_table_names():
        return False
    return column in {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    cols = [
        ("professor_id", sa.Column("professor_id", PG_UUID(as_uuid=True), sa.ForeignKey("professores.id"), nullable=True)),
        ("professor_nome_externo", sa.Column("professor_nome_externo", sa.String(255), nullable=True)),
        ("regular", sa.Column("regular", sa.String(10), nullable=False, server_default="Sim")),
        ("ticket_number", sa.Column("ticket_number", sa.String(100), nullable=True)),
        ("start_time", sa.Column("start_time", sa.Time(), nullable=True)),
        ("end_time", sa.Column("end_time", sa.Time(), nullable=True)),
    ]
    for name, col in cols:
        if not _column_exists("image_director_reports", name):
            op.add_column("image_director_reports", col)

    op.execute(
        """
        UPDATE image_director_reports idr
        SET professor_nome_externo = sub.professor_nome
        FROM (
            SELECT DISTINCT ON (report_id) report_id, professor_nome
            FROM image_director_lessons
            WHERE professor_nome IS NOT NULL AND TRIM(professor_nome) <> ''
            ORDER BY report_id, numero_aula
        ) sub
        WHERE idr.id = sub.report_id
          AND (idr.professor_nome_externo IS NULL OR TRIM(idr.professor_nome_externo) = '')
        """
    )


def downgrade() -> None:
    for name in (
        "end_time",
        "start_time",
        "ticket_number",
        "regular",
        "professor_nome_externo",
        "professor_id",
    ):
        if _column_exists("image_director_reports", name):
            op.drop_column("image_director_reports", name)
