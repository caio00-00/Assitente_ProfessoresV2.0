"""v5: tabelas aulas e aulas_sincronizacao

A aula prevista vira um registro, calculado da grade vigente, da Agenda e dos
relatórios (app/modulos/aulas/servico.py). Só cria tabelas novas; nada existente
é alterado. As aulas são preenchidas sob demanda (ao abrir a tela Aulas) ou pela
rota /api/v1/aulas/sincronizar.

Revision ID: v5a1b2c3d4e5
Revises: v4b2c3d4e5f6
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "v5a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "v4b2c3d4e5f6"
branch_labels = None
depends_on = None


def _tabelas():
    return set(inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    tabelas = _tabelas()
    if "aulas" not in tabelas:
        op.create_table(
            "aulas",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("data", sa.Date(), nullable=False),
            sa.Column("turma_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("turmas.id"), nullable=True),
            sa.Column("disciplina_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("disciplinas.id"), nullable=True),
            sa.Column("professor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("professores.id"), nullable=True),
            sa.Column("estudio_id", sa.Integer(), sa.ForeignKey("estudio.id"), nullable=True),
            sa.Column("inicio", sa.Time(), nullable=True),
            sa.Column("fim", sa.Time(), nullable=True),
            sa.Column("horario_texto", sa.String(50), nullable=True),
            sa.Column("tipo", sa.String(30), nullable=False, server_default="aula"),
            sa.Column("origem", sa.String(20), nullable=False, server_default="grade"),
            sa.Column("grade_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("grades.id", ondelete="SET NULL"), nullable=True),
            sa.Column("agendamento_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("agenda_agendamentos.id", ondelete="SET NULL"), nullable=True),
            sa.Column("remanejada", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("cancelada_na_agenda", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("motivo_cancelamento", sa.Text(), nullable=True),
            sa.Column("fora_da_grade", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("class_report_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("class_reports.id", ondelete="SET NULL"), nullable=True),
            sa.Column("image_director_report_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("image_director_reports.id", ondelete="SET NULL"), nullable=True),
            sa.Column("image_director_lesson_id", postgresql.UUID(as_uuid=True),
                      sa.ForeignKey("image_director_lessons.id", ondelete="SET NULL"), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, server_default="prevista"),
            sa.Column("tem_video", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("tem_pdf", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("cobrar", sa.String(80), nullable=True),
            sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("atualizado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_aulas_data", "aulas", ["data"])
        op.create_index("ix_aulas_turma_id", "aulas", ["turma_id"])
        op.create_index("ix_aulas_estudio_id", "aulas", ["estudio_id"])
        op.create_index("ix_aulas_status", "aulas", ["status"])
        op.create_index("ix_aulas_class_report_id", "aulas", ["class_report_id"])
        op.create_index("ix_aulas_image_director_report_id", "aulas", ["image_director_report_id"])
        op.create_index("ix_aulas_data_status", "aulas", ["data", "status"])
        op.create_index("ux_aulas_data_grade", "aulas", ["data", "grade_id"], unique=True,
                        postgresql_where=sa.text("grade_id IS NOT NULL"))
        op.create_index("ux_aulas_data_agendamento", "aulas", ["data", "agendamento_id"], unique=True,
                        postgresql_where=sa.text("agendamento_id IS NOT NULL"))
        op.create_index("ux_aulas_class_report", "aulas", ["class_report_id"], unique=True,
                        postgresql_where=sa.text("class_report_id IS NOT NULL"))
    if "aulas_sincronizacao" not in tabelas:
        op.create_table(
            "aulas_sincronizacao",
            sa.Column("data", sa.Date(), primary_key=True),
            sa.Column("assinatura", sa.String(64), nullable=False),
            sa.Column("sincronizado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    tabelas = _tabelas()
    if "aulas_sincronizacao" in tabelas:
        op.drop_table("aulas_sincronizacao")
    if "aulas" in tabelas:
        op.drop_table("aulas")
