"""image_director_por_disciplina: 1 relatório por disciplina (v3.3)

Revision ID: a1b2c3d4e5f7
Revises: f7a8b9c0d1e2
Create Date: 2026-09-01 14:00:00.000000

- Adiciona disciplina_id, disciplina_nome e horario_aula ao cabeçalho
- Troca índice único de (turno+estúdio) para (turno+estúdio+disciplina)
- Backfill a partir da primeira aula do relatório (legado)

Idempotente — apenas ADD COLUMN e recria índice se necessário.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, Sequence[str], None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in inspect(bind).get_table_names()


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    if not _table_exists(table):
        return False
    return column in {c["name"] for c in inspect(bind).get_columns(table)}


def _index_exists(table: str, index: str) -> bool:
    bind = op.get_bind()
    if not _table_exists(table):
        return False
    return index in {idx["name"] for idx in inspect(bind).get_indexes(table)}


def upgrade() -> None:
    if not _table_exists("image_director_reports"):
        return

    if not _column_exists("image_director_reports", "disciplina_id"):
        op.add_column(
            "image_director_reports",
            sa.Column(
                "disciplina_id",
                PG_UUID(as_uuid=True),
                sa.ForeignKey("disciplinas.id"),
                nullable=True,
            ),
        )
    if not _column_exists("image_director_reports", "disciplina_nome"):
        op.add_column(
            "image_director_reports",
            sa.Column("disciplina_nome", sa.String(255), nullable=True),
        )
    if not _column_exists("image_director_reports", "horario_aula"):
        op.add_column(
            "image_director_reports",
            sa.Column("horario_aula", sa.String(100), nullable=True),
        )

    # Backfill legado: puxa disciplina da primeira aula vinculada
    op.execute(
        text("""
            UPDATE image_director_reports r
            SET disciplina_nome = sub.disciplina_nome
            FROM (
                SELECT DISTINCT ON (report_id)
                    report_id, disciplina_nome
                FROM image_director_lessons
                ORDER BY report_id, numero_aula
            ) sub
            WHERE r.id = sub.report_id
              AND r.disciplina_nome IS NULL
              AND sub.disciplina_nome IS NOT NULL
        """)
    )
    op.execute(
        text("""
            UPDATE image_director_reports r
            SET disciplina_id = d.id
            FROM disciplinas d
            WHERE r.disciplina_id IS NULL
              AND r.disciplina_nome IS NOT NULL
              AND lower(trim(d.nome)) = lower(trim(r.disciplina_nome))
        """)
    )

    if _index_exists("image_director_reports", "uq_image_director_report_turno"):
        op.drop_index("uq_image_director_report_turno", table_name="image_director_reports")

    if not _index_exists("image_director_reports", "uq_image_director_report_disciplina"):
        op.create_index(
            "uq_image_director_report_disciplina",
            "image_director_reports",
            [
                "diretor_imagem_id",
                "data_relatorio",
                "turno",
                "estudio",
                "disciplina_id",
            ],
            unique=True,
            postgresql_where=sa.text(
                "is_deleted = false AND disciplina_id IS NOT NULL"
            ),
        )


def downgrade() -> None:
    if not _table_exists("image_director_reports"):
        return

    if _index_exists("image_director_reports", "uq_image_director_report_disciplina"):
        op.drop_index(
            "uq_image_director_report_disciplina",
            table_name="image_director_reports",
        )

    if not _index_exists("image_director_reports", "uq_image_director_report_turno"):
        op.create_index(
            "uq_image_director_report_turno",
            "image_director_reports",
            ["diretor_imagem_id", "data_relatorio", "turno", "estudio"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        )

    if _column_exists("image_director_reports", "horario_aula"):
        op.drop_column("image_director_reports", "horario_aula")
    if _column_exists("image_director_reports", "disciplina_nome"):
        op.drop_column("image_director_reports", "disciplina_nome")
    if _column_exists("image_director_reports", "disciplina_id"):
        op.drop_column("image_director_reports", "disciplina_id")
