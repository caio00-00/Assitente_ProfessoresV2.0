"""v4: histórico de versões, cancelamento rastreável, nome normalizado, tentativas de login

Revision ID: v4a1b2c3d4e5
Revises: h0i1j2k3l4m5
Create Date: 2026-11-11 10:00:00.000000

Pode rodar mais de uma vez: só cria o que ainda não existe.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "v4a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "h0i1j2k3l4m5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tabelas():
    return set(inspect(op.get_bind()).get_table_names())


def _colunas(tabela):
    if tabela not in _tabelas():
        return set()
    return {c["name"] for c in inspect(op.get_bind()).get_columns(tabela)}


def _indices(tabela):
    if tabela not in _tabelas():
        return set()
    return {i["name"] for i in inspect(op.get_bind()).get_indexes(tabela)}


def _json():
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.JSONB()
    return sa.JSON()


def _uuid():
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.UUID(as_uuid=True)
    return sa.String(36)


def upgrade() -> None:
    # 1. Cancelamento rastreável nos dois relatórios
    for tabela in ("class_reports", "image_director_reports"):
        cols = _colunas(tabela)
        if not cols:
            continue
        if "justificativa_cancelamento" not in cols:
            op.add_column(tabela, sa.Column("justificativa_cancelamento", sa.Text(), nullable=True))
        if "cancelado_por" not in cols:
            op.add_column(tabela, sa.Column("cancelado_por", _uuid(), sa.ForeignKey("users.id"), nullable=True))
        if "cancelado_em" not in cols:
            op.add_column(tabela, sa.Column("cancelado_em", sa.DateTime(timezone=True), nullable=True))

    # 2. Nome do arquivo normalizado (busca do Vimeo e verificadores)
    if "nome_normalizado" not in _colunas("class_reports"):
        op.add_column("class_reports", sa.Column("nome_normalizado", sa.String(500), nullable=True))
    if "class_reports" in _tabelas() and "ix_class_reports_nome_normalizado" not in _indices("class_reports"):
        op.create_index("ix_class_reports_nome_normalizado", "class_reports", ["nome_normalizado"])

    # 3. Histórico de versões
    if "report_versions" not in _tabelas():
        op.create_table(
            "report_versions",
            sa.Column("id", _uuid(), primary_key=True),
            sa.Column("tipo", sa.String(40), nullable=False),
            sa.Column("report_id", _uuid(), nullable=False),
            sa.Column("versao", sa.Integer(), nullable=False),
            sa.Column("evento", sa.String(30), nullable=False),
            sa.Column("status_anterior", sa.String(30), nullable=True),
            sa.Column("status_novo", sa.String(30), nullable=True),
            sa.Column("alteracoes", _json(), nullable=True),
            sa.Column("snapshot", _json(), nullable=False),
            sa.Column("motivo", sa.Text(), nullable=True),
            sa.Column("alterado_por", _uuid(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("alterado_em", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("tipo", "report_id", "versao", name="uq_report_versions_tipo_report_versao"),
        )
        op.create_index("ix_report_versions_report", "report_versions", ["tipo", "report_id"])

    # 4. Tentativas de login
    if "login_attempts" not in _tabelas():
        op.create_table(
            "login_attempts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("ip", sa.String(64), nullable=True),
            sa.Column("sucesso", sa.String(1), nullable=False, server_default="N"),
            sa.Column("criado_em", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_login_attempts_email_quando", "login_attempts", ["email", "criado_em"])

    # 5. Preenche o nome normalizado dos relatórios que já têm nome gerado
    if "nome_normalizado" in _colunas("class_reports"):
        from app.utils.text_utils import normalizar_para_match

        bind = op.get_bind()
        linhas = bind.execute(
            sa.text(
                "SELECT id, nome_ficheiro_gerado FROM class_reports "
                "WHERE nome_ficheiro_gerado IS NOT NULL AND nome_normalizado IS NULL"
            )
        ).fetchall()
        for rid, nome in linhas:
            bind.execute(
                sa.text("UPDATE class_reports SET nome_normalizado = :n WHERE id = :i"),
                {"n": normalizar_para_match(nome), "i": rid},
            )


def downgrade() -> None:
    for tabela in ("login_attempts", "report_versions"):
        if tabela in _tabelas():
            op.drop_table(tabela)
    if "ix_class_reports_nome_normalizado" in _indices("class_reports"):
        op.drop_index("ix_class_reports_nome_normalizado", table_name="class_reports")
    if "nome_normalizado" in _colunas("class_reports"):
        op.drop_column("class_reports", "nome_normalizado")
    for tabela in ("class_reports", "image_director_reports"):
        for col in ("cancelado_em", "cancelado_por", "justificativa_cancelamento"):
            if col in _colunas(tabela):
                op.drop_column(tabela, col)
