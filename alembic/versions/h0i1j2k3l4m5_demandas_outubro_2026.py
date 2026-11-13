"""demandas_outubro_2026: antecipacao, mes de referencia, campos evento e chave transmissao

Revision ID: h0i1j2k3l4m5
Revises: g9h0i1j2k3l4
Create Date: 2026-10-18 14:15:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "h0i1j2k3l4m5"
down_revision: Union[str, Sequence[str], None] = "g9h0i1j2k3l4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    if table not in inspect(bind).get_table_names():
        return False
    return column in {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    # 1. image_director_reports
    idr_cols = [
        ("chave_transmissao", sa.Column("chave_transmissao", sa.String(255), nullable=True)),
        ("nome_evento", sa.Column("nome_evento", sa.String(255), nullable=True)),
        ("departamento_solicitante", sa.Column("departamento_solicitante", sa.String(120), nullable=True)),
        ("responsavel_evento", sa.Column("responsavel_evento", sa.String(255), nullable=True)),
        ("solicitante_antecipacao", sa.Column("solicitante_antecipacao", sa.String(20), nullable=True)),
        ("data_referencia", sa.Column("data_referencia", sa.Date(), nullable=True)),
        ("motivo_referencia", sa.Column("motivo_referencia", sa.String(255), nullable=True)),
    ]
    for name, col in idr_cols:
        if not _column_exists("image_director_reports", name):
            op.add_column("image_director_reports", col)

    # 2. agenda_agendamentos
    agenda_cols = [
        ("chave_transmissao", sa.Column("chave_transmissao", sa.String(255), nullable=True)),
        ("nome_evento", sa.Column("nome_evento", sa.String(255), nullable=True)),
        ("responsavel_evento", sa.Column("responsavel_evento", sa.String(255), nullable=True)),
        ("solicitante_antecipacao", sa.Column("solicitante_antecipacao", sa.String(20), nullable=True)),
        ("data_referencia", sa.Column("data_referencia", sa.Date(), nullable=True)),
        ("motivo_referencia", sa.Column("motivo_referencia", sa.String(255), nullable=True)),
    ]
    for name, col in agenda_cols:
        if not _column_exists("agenda_agendamentos", name):
            op.add_column("agenda_agendamentos", col)

    # 3. class_reports
    class_report_cols = [
        ("data_execucao_real", sa.Column("data_execucao_real", sa.Date(), nullable=True)),
        ("data_referencia_aula", sa.Column("data_referencia_aula", sa.Date(), nullable=True)),
        ("solicitante_antecipacao", sa.Column("solicitante_antecipacao", sa.String(20), nullable=True)),
        ("motivo_referencia", sa.Column("motivo_referencia", sa.String(255), nullable=True)),
    ]
    for name, col in class_report_cols:
        if not _column_exists("class_reports", name):
            op.add_column("class_reports", col)


def downgrade() -> None:
    # 3. class_reports
    for name in (
        "motivo_referencia",
        "solicitante_antecipacao",
        "data_referencia_aula",
        "data_execucao_real",
    ):
        if _column_exists("class_reports", name):
            op.drop_column("class_reports", name)

    # 2. agenda_agendamentos
    for name in (
        "motivo_referencia",
        "data_referencia",
        "solicitante_antecipacao",
        "responsavel_evento",
        "nome_evento",
        "chave_transmissao",
    ):
        if _column_exists("agenda_agendamentos", name):
            op.drop_column("agenda_agendamentos", name)

    # 1. image_director_reports
    for name in (
        "motivo_referencia",
        "data_referencia",
        "solicitante_antecipacao",
        "responsavel_evento",
        "departamento_solicitante",
        "nome_evento",
        "chave_transmissao",
    ):
        if _column_exists("image_director_reports", name):
            op.drop_column("image_director_reports", name)
