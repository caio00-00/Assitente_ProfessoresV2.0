"""v4.1: class_reports.compliance_verificado_em

Guarda quando a busca no Drive olhou o relatório pela última vez. Usada pela
varredura sem worker (Vercel), que começa pelos relatórios há mais tempo sem
verificação. Só adiciona uma coluna; pode rodar mais de uma vez.

Revision ID: v4b2c3d4e5f6
Revises: v4a1b2c3d4e5
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "v4b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "v4a1b2c3d4e5"
branch_labels = None
depends_on = None


def _colunas():
    return {c["name"] for c in inspect(op.get_bind()).get_columns("class_reports")}


def upgrade() -> None:
    if "compliance_verificado_em" not in _colunas():
        op.add_column("class_reports", sa.Column("compliance_verificado_em", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    if "compliance_verificado_em" in _colunas():
        op.drop_column("class_reports", "compliance_verificado_em")
