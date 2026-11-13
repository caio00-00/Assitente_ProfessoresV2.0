"""class_report_validacao_coordenacao: fluxo v3.1 em class_reports

Revision ID: e4f6a8b0c2d3
Revises: d3e5f7a9b1c2
Create Date: 2026-09-01 00:00:00.000000

Operação SEGURA — não apaga nem altera dados existentes:
    - Apenas ADD COLUMN (nullable ou com default false)
    - Registros atuais permanecem intactos; novos campos ficam NULL/false
    - Amplia o tamanho de status (20 → 30) sem truncar valores existentes
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

# revision identifiers, used by Alembic.
revision: str = "e4f6a8b0c2d3"
down_revision: Union[str, Sequence[str], None] = "d3e5f7a9b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _class_report_columns() -> set[str]:
    bind = op.get_bind()
    inspector = inspect(bind)
    return {col["name"] for col in inspector.get_columns("class_reports")}


def upgrade() -> None:
    cols = _class_report_columns()

    if "precisa_correcao" not in cols:
        op.add_column(
            "class_reports",
            sa.Column(
                "precisa_correcao",
                sa.Boolean(),
                nullable=False,
                server_default="false",
            ),
        )

    if "observacao_coordenacao" not in cols:
        op.add_column(
            "class_reports",
            sa.Column("observacao_coordenacao", sa.Text(), nullable=True),
        )

    if "validado_por" not in cols:
        op.add_column(
            "class_reports",
            sa.Column(
                "validado_por",
                PG_UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
        )

    if "validado_em" not in cols:
        op.add_column(
            "class_reports",
            sa.Column("validado_em", sa.DateTime(timezone=True), nullable=True),
        )

    # Amplia VARCHAR apenas se ainda estiver no tamanho antigo (idempotente).
    status_col = next(
        (c for c in inspect(op.get_bind()).get_columns("class_reports") if c["name"] == "status"),
        None,
    )
    if status_col and getattr(status_col.get("type"), "length", None) == 20:
        op.alter_column(
            "class_reports",
            "status",
            existing_type=sa.String(length=20),
            type_=sa.String(length=30),
            existing_nullable=False,
        )


def downgrade() -> None:
    cols = _class_report_columns()

    status_col = next(
        (c for c in inspect(op.get_bind()).get_columns("class_reports") if c["name"] == "status"),
        None,
    )
    if status_col and getattr(status_col.get("type"), "length", None) == 30:
        op.alter_column(
            "class_reports",
            "status",
            existing_type=sa.String(length=30),
            type_=sa.String(length=20),
            existing_nullable=False,
        )

    if "validado_em" in cols:
        op.drop_column("class_reports", "validado_em")
    if "validado_por" in cols:
        op.drop_column("class_reports", "validado_por")
    if "observacao_coordenacao" in cols:
        op.drop_column("class_reports", "observacao_coordenacao")
    if "precisa_correcao" in cols:
        op.drop_column("class_reports", "precisa_correcao")
