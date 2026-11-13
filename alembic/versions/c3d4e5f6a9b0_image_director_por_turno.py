"""image_director_por_turno: 1 relatório por turno com várias aulas (v3.3)

Revision ID: c3d4e5f6a9b0
Revises: b2c3d4e5f6a8
Create Date: 2026-09-01 16:00:00.000000

- Consolida relatórios duplicados do mesmo turno (mescla aulas no mais antigo)
- Troca índice único de disciplina para turno+estúdio
- Idempotente — não apaga linhas de aulas, apenas soft-delete de cabeçalhos duplicados
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision: str = "c3d4e5f6a9b0"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in inspect(bind).get_table_names()


def _index_exists(table: str, index: str) -> bool:
    bind = op.get_bind()
    if not _table_exists(table):
        return False
    return index in {idx["name"] for idx in inspect(bind).get_indexes(table)}


def upgrade() -> None:
    if not _table_exists("image_director_reports"):
        return

    # Mescla aulas de cabeçalhos duplicados (legado "1 por disciplina") no registro mais antigo
    op.execute(
        text("""
            WITH ranked AS (
                SELECT
                    id,
                    diretor_imagem_id,
                    data_relatorio,
                    turno,
                    estudio,
                    ROW_NUMBER() OVER (
                        PARTITION BY diretor_imagem_id, data_relatorio, turno, estudio
                        ORDER BY created_at ASC
                    ) AS rn
                FROM image_director_reports
                WHERE is_deleted = false
            ),
            keepers AS (
                SELECT id AS keeper_id, diretor_imagem_id, data_relatorio, turno, estudio
                FROM ranked
                WHERE rn = 1
            ),
            dupes AS (
                SELECT r.id AS dupe_id, k.keeper_id
                FROM ranked r
                JOIN keepers k
                  ON k.diretor_imagem_id = r.diretor_imagem_id
                 AND k.data_relatorio = r.data_relatorio
                 AND k.turno = r.turno
                 AND k.estudio = r.estudio
                WHERE r.rn > 1
            )
            UPDATE image_director_lessons l
            SET report_id = d.keeper_id
            FROM dupes d
            WHERE l.report_id = d.dupe_id
        """)
    )
    op.execute(
        text("""
            WITH ranked AS (
                SELECT
                    id,
                    diretor_imagem_id,
                    data_relatorio,
                    turno,
                    estudio,
                    ROW_NUMBER() OVER (
                        PARTITION BY diretor_imagem_id, data_relatorio, turno, estudio
                        ORDER BY created_at ASC
                    ) AS rn
                FROM image_director_reports
                WHERE is_deleted = false
            )
            UPDATE image_director_reports r
            SET is_deleted = true
            FROM ranked x
            WHERE r.id = x.id AND x.rn > 1
        """)
    )

    if _index_exists("image_director_reports", "uq_image_director_report_disciplina"):
        op.drop_index("uq_image_director_report_disciplina", table_name="image_director_reports")

    if not _index_exists("image_director_reports", "uq_image_director_report_turno"):
        op.create_index(
            "uq_image_director_report_turno",
            "image_director_reports",
            ["diretor_imagem_id", "data_relatorio", "turno", "estudio"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        )


def downgrade() -> None:
    if not _table_exists("image_director_reports"):
        return

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
