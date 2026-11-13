"""add_unique_constraint_class_report

Revision ID: f52c41ff3b37
Revises: 3c16c0febece
Create Date: 2026-05-02 14:07:20.702823

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f52c41ff3b37'
down_revision: Union[str, Sequence[str], None] = '3c16c0febece'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Passo 1: Remove duplicados mantendo o registro mais recente (maior id)
    # para cada combinação de (turma_id, data_aula, horario_aula)
    op.execute("""
        DELETE FROM class_reports
        WHERE id NOT IN (
            SELECT MAX(id::text)::uuid
            FROM class_reports
            WHERE is_deleted = false OR is_deleted IS NULL
            GROUP BY turma_id, data_aula, horario_aula
        )
        AND (is_deleted = false OR is_deleted IS NULL)
    """)

    # Passo 2: Cria a constraint após a limpeza
    op.create_index(
        'uq_class_report_turma_data_horario',
        'class_reports',
        ['turma_id', 'data_aula', 'horario_aula'],
        unique=True,
        postgresql_where=sa.text("is_deleted = false OR is_deleted IS NULL")
    )

def downgrade() -> None:
    op.drop_index(
        'uq_class_report_turma_data_horario',
        table_name='class_reports'
    )
