"""image_director_origem_vinculo: class_report_id + origem (grade | gravacao_estudio)

Revision ID: f8a9b0c1d2e3
Revises: e5f6a7b8c9d0
Create Date: 2026-09-03 14:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    if table not in inspect(bind).get_table_names():
        return False
    return column in {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    if not _column_exists("image_director_reports", "class_report_id"):
        op.add_column(
            "image_director_reports",
            sa.Column(
                "class_report_id",
                PG_UUID(as_uuid=True),
                sa.ForeignKey("class_reports.id"),
                nullable=True,
            ),
        )
    if not _column_exists("image_director_reports", "origem"):
        op.add_column(
            "image_director_reports",
            sa.Column(
                "origem",
                sa.String(30),
                nullable=False,
                server_default="grade",
            ),
        )


def downgrade() -> None:
    if _column_exists("image_director_reports", "origem"):
        op.drop_column("image_director_reports", "origem")
    if _column_exists("image_director_reports", "class_report_id"):
        op.drop_column("image_director_reports", "class_report_id")
