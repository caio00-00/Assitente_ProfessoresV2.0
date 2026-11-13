"""diretor_imagem_validacao: fluxo de validação por Diretor-Chefe (v3.2)

Revision ID: d3e5f7a9b1c2
Revises: c9f1a2b3d4e5
Create Date: 2026-08-19 00:00:00.000001

Idempotente: ignora colunas que já existem.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# revision identifiers, used by Alembic.
revision: str = "d3e5f7a9b1c2"
down_revision: Union[str, Sequence[str], None] = "c9f1a2b3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    if not _column_exists("image_director_reports", "precisa_correcao"):
        op.add_column(
            "image_director_reports",
            sa.Column("precisa_correcao", sa.Boolean(), nullable=False, server_default="false"),
        )
    if not _column_exists("image_director_reports", "observacao_coordenacao"):
        op.add_column(
            "image_director_reports",
            sa.Column("observacao_coordenacao", sa.Text(), nullable=True),
        )
    if not _column_exists("image_director_reports", "validado_por"):
        op.add_column(
            "image_director_reports",
            sa.Column(
                "validado_por", PG_UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
            ),
        )
    if not _column_exists("image_director_reports", "validado_em"):
        op.add_column(
            "image_director_reports",
            sa.Column("validado_em", sa.DateTime(timezone=True), nullable=True),
        )

    if not _column_exists("image_director_lessons", "video_corrompido_obs"):
        op.add_column(
            "image_director_lessons",
            sa.Column("video_corrompido_obs", sa.Text(), nullable=True),
        )
    if not _column_exists("image_director_lessons", "problema_audio_obs"):
        op.add_column(
            "image_director_lessons",
            sa.Column("problema_audio_obs", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if _column_exists("image_director_lessons", "problema_audio_obs"):
        op.drop_column("image_director_lessons", "problema_audio_obs")
    if _column_exists("image_director_lessons", "video_corrompido_obs"):
        op.drop_column("image_director_lessons", "video_corrompido_obs")

    if _column_exists("image_director_reports", "validado_em"):
        op.drop_column("image_director_reports", "validado_em")
    if _column_exists("image_director_reports", "validado_por"):
        op.drop_column("image_director_reports", "validado_por")
    if _column_exists("image_director_reports", "observacao_coordenacao"):
        op.drop_column("image_director_reports", "observacao_coordenacao")
    if _column_exists("image_director_reports", "precisa_correcao"):
        op.drop_column("image_director_reports", "precisa_correcao")
