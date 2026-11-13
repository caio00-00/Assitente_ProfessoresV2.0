"""soft_delete_partial_unique_index

Revision ID: e8a0614a9e08
Revises: e1f2a3b4c5d6
Create Date: 2026-05-29 18:45:06.282084

Substitui o UniqueConstraint hard por um índice único parcial que ignora
registros com is_deleted = TRUE, permitindo recriar relatórios após soft-delete.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e8a0614a9e08'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove a constraint de unicidade absoluta (inclui registros soft-deletados)
    op.drop_constraint('uq_class_report_turma_data_horario', 'class_reports', type_='unique')

    # Cria índice único parcial — só considera relatórios NÃO deletados
    op.create_index(
        'uq_class_report_turma_data_horario',
        'class_reports',
        ['turma_id', 'data_aula', 'horario_aula', 'disciplina_id'],
        unique=True,
        postgresql_where=sa.text('is_deleted = FALSE'),
    )


def downgrade() -> None:
    op.drop_index('uq_class_report_turma_data_horario', table_name='class_reports')
    op.create_unique_constraint(
        'uq_class_report_turma_data_horario',
        'class_reports',
        ['turma_id', 'data_aula', 'horario_aula', 'disciplina_id'],
    )
