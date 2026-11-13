"""diretor_imagem_report: Relatório do Diretor de Imagem (v3.2)

Revision ID: c9f1a2b3d4e5
Revises: b2d4e6f8a0c1
Create Date: 2026-08-19 00:00:00.000000

Mudanças:
    1. diretores_imagem.user_id — vincula o cadastro a um usuário com login
    2. image_director_reports — cabeçalho do relatório de turno do diretor de imagem
    3. image_director_lessons — blocos "AULA 0X" dentro do relatório
    4. image_director_checklist_items — catálogo de itens de fechamento de estúdio
    5. image_director_checklist_responses — respostas do checklist por relatório
    6. image_director_custom_questions — perguntas extras cadastradas pelo Diretor-Chefe
    7. image_director_custom_answers — respostas às perguntas extras

Idempotente: ignora objetos que já existem (produção pode ter sido criada manualmente).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# revision identifiers, used by Alembic.
revision: str = "c9f1a2b3d4e5"
down_revision: Union[str, Sequence[str], None] = "b2d4e6f8a0c1"
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


def _constraint_exists(table: str, constraint: str) -> bool:
    bind = op.get_bind()
    if not _table_exists(table):
        return False
    return constraint in {
        uc["name"] for uc in inspect(bind).get_unique_constraints(table)
    }


def upgrade() -> None:
    if not _column_exists("diretores_imagem", "user_id"):
        op.add_column(
            "diretores_imagem",
            sa.Column("user_id", PG_UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        )
    if not _constraint_exists("diretores_imagem", "uq_diretores_imagem_user_id"):
        op.create_unique_constraint(
            "uq_diretores_imagem_user_id", "diretores_imagem", ["user_id"]
        )

    if not _table_exists("image_director_reports"):
        op.create_table(
            "image_director_reports",
            sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
            sa.Column("created_by", PG_UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="RASCUNHO"),
            sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "diretor_imagem_id",
                PG_UUID(as_uuid=True),
                sa.ForeignKey("diretores_imagem.id"),
                nullable=False,
            ),
            sa.Column("data_relatorio", sa.Date(), nullable=False),
            sa.Column("turno", sa.String(20), nullable=False),
            sa.Column("estudio", sa.String(50), nullable=False),
            sa.Column("turma_id", PG_UUID(as_uuid=True), sa.ForeignKey("turmas.id"), nullable=True),
            sa.Column("serie_modulo_manual", sa.String(255), nullable=True),
            sa.Column("horario_entrada", sa.Time(), nullable=True),
            sa.Column("horario_saida", sa.Time(), nullable=True),
            sa.Column("youtube_link", sa.String(1000), nullable=True),
            sa.Column("observacoes_gerais", sa.Text(), nullable=True),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        )

    if not _index_exists("image_director_reports", "uq_image_director_report_turno"):
        op.create_index(
            "uq_image_director_report_turno",
            "image_director_reports",
            ["diretor_imagem_id", "data_relatorio", "turno", "estudio"],
            unique=True,
            postgresql_where=sa.text("is_deleted = false"),
        )

    if not _table_exists("image_director_lessons"):
        op.create_table(
            "image_director_lessons",
            sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "report_id",
                PG_UUID(as_uuid=True),
                sa.ForeignKey("image_director_reports.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("numero_aula", sa.Integer(), nullable=False),
            sa.Column(
                "class_report_id",
                PG_UUID(as_uuid=True),
                sa.ForeignKey("class_reports.id"),
                nullable=True,
            ),
            sa.Column("disciplina_nome", sa.String(255), nullable=False),
            sa.Column("professor_nome", sa.String(255), nullable=False),
            sa.Column("transmissao_ou_gravada", sa.String(20), nullable=False),
            sa.Column("video_corrompido", sa.String(10), nullable=False, server_default="Não"),
            sa.Column("interrupcoes", sa.String(10), nullable=False, server_default="Não"),
            sa.Column("problema_audio", sa.String(10), nullable=False, server_default="Não"),
            sa.Column("vinhetas_corretas", sa.String(10), nullable=False, server_default="Sim"),
            sa.Column("creditos_corretos", sa.String(10), nullable=False, server_default="Sim"),
            sa.Column("observacoes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not _table_exists("image_director_checklist_items"):
        op.create_table(
            "image_director_checklist_items",
            sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
            sa.Column("nome", sa.String(255), nullable=False),
            sa.Column("ativo", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not _table_exists("image_director_checklist_responses"):
        op.create_table(
            "image_director_checklist_responses",
            sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "report_id",
                PG_UUID(as_uuid=True),
                sa.ForeignKey("image_director_reports.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "item_id",
                PG_UUID(as_uuid=True),
                sa.ForeignKey("image_director_checklist_items.id"),
                nullable=False,
            ),
            sa.Column("resposta", sa.Boolean(), nullable=True),
        )

    if not _table_exists("image_director_custom_questions"):
        op.create_table(
            "image_director_custom_questions",
            sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
            sa.Column("texto", sa.Text(), nullable=False),
            sa.Column("tipo", sa.String(20), nullable=False, server_default="sim_nao"),
            sa.Column("nivel", sa.String(20), nullable=False, server_default="por_relatorio"),
            sa.Column("obrigatoria", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("ativa", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_by", PG_UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    if not _table_exists("image_director_custom_answers"):
        op.create_table(
            "image_director_custom_answers",
            sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "question_id",
                PG_UUID(as_uuid=True),
                sa.ForeignKey("image_director_custom_questions.id"),
                nullable=False,
            ),
            sa.Column(
                "report_id",
                PG_UUID(as_uuid=True),
                sa.ForeignKey("image_director_reports.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column(
                "lesson_id",
                PG_UUID(as_uuid=True),
                sa.ForeignKey("image_director_lessons.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("resposta_texto", sa.Text(), nullable=True),
            sa.Column("resposta_bool", sa.Boolean(), nullable=True),
        )


def downgrade() -> None:
    if _table_exists("image_director_custom_answers"):
        op.drop_table("image_director_custom_answers")
    if _table_exists("image_director_custom_questions"):
        op.drop_table("image_director_custom_questions")
    if _table_exists("image_director_checklist_responses"):
        op.drop_table("image_director_checklist_responses")
    if _table_exists("image_director_checklist_items"):
        op.drop_table("image_director_checklist_items")
    if _table_exists("image_director_lessons"):
        op.drop_table("image_director_lessons")
    if _index_exists("image_director_reports", "uq_image_director_report_turno"):
        op.drop_index("uq_image_director_report_turno", table_name="image_director_reports")
    if _table_exists("image_director_reports"):
        op.drop_table("image_director_reports")
    if _constraint_exists("diretores_imagem", "uq_diretores_imagem_user_id"):
        op.drop_constraint("uq_diretores_imagem_user_id", "diretores_imagem", type_="unique")
    if _column_exists("diretores_imagem", "user_id"):
        op.drop_column("diretores_imagem", "user_id")
