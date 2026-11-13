"""grade_horaria_v2

Revision ID: 1e87efa00b86
Revises: e8a0614a9e08
Create Date: 2026-06-02 16:46:57.449026

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1e87efa00b86'
down_revision: Union[str, Sequence[str], None] = 'e8a0614a9e08'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(bind, table_name: str) -> bool:
    return sa.inspect(bind).has_table(table_name)


def _has_column(bind, table_name: str, column_name: str) -> bool:
    cols = [c["name"] for c in sa.inspect(bind).get_columns(table_name)]
    return column_name in cols


def _has_index(bind, table_name: str, index_name: str) -> bool:
    indexes = sa.inspect(bind).get_indexes(table_name)
    return any(i["name"] == index_name for i in indexes)


def upgrade() -> None:
    """Upgrade schema — idempotente: verifica existência antes de cada operação."""
    bind = op.get_bind()

    # --- 1. Criar tabelas de infraestrutura (sem FKs entre elas) ---
    if not _has_table(bind, 'canal_iptv'):
        op.create_table('canal_iptv',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('nome', sa.String(length=100), nullable=False),
            sa.Column('numero', sa.Integer(), nullable=False),
            sa.Column('ativo', sa.Boolean(), nullable=False),
            sa.Column('data_criacao', sa.TIMESTAMP(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('numero')
        )
    if not _has_table(bind, 'estudio'):
        op.create_table('estudio',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('nome', sa.String(length=100), nullable=False),
            sa.Column('horario_inicio', sa.Time(), nullable=False),
            sa.Column('horario_fim', sa.Time(), nullable=False),
            sa.Column('funciona_24h', sa.Boolean(), nullable=False),
            sa.Column('ativo', sa.Boolean(), nullable=False),
            sa.Column('data_criacao', sa.TIMESTAMP(), nullable=False),
            sa.PrimaryKeyConstraint('id')
        )
    if not _has_table(bind, 'slot_horario'):
        op.create_table('slot_horario',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('turno', sa.String(length=20), nullable=False),
            sa.Column('ordem', sa.Integer(), nullable=False),
            sa.Column('horario_inicio', sa.Time(), nullable=False),
            sa.Column('horario_fim', sa.Time(), nullable=False),
            sa.Column('ativo', sa.Boolean(), nullable=False),
            sa.Column('data_criacao', sa.TIMESTAMP(), nullable=False),
            sa.CheckConstraint("turno IN ('manha','tarde','noite','madrugada')", name='chk_turno'),
            sa.CheckConstraint('horario_fim > horario_inicio', name='chk_horario'),
            sa.PrimaryKeyConstraint('id')
        )

    # --- 2. Criar grade_versao (FK -> turmas, users) ---
    if not _has_table(bind, 'grade_versao'):
        op.create_table('grade_versao',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('turma_id', sa.UUID(), nullable=False),
            sa.Column('is_active', sa.Boolean(), nullable=False),
            sa.Column('data_ativacao', sa.TIMESTAMP(), nullable=True),
            sa.Column('data_criacao', sa.TIMESTAMP(), nullable=False),
            sa.Column('criado_por', sa.UUID(), nullable=True),
            sa.ForeignKeyConstraint(['criado_por'], ['users.id'], ),
            sa.ForeignKeyConstraint(['turma_id'], ['turmas.id'], ),
            sa.PrimaryKeyConstraint('id')
        )

    # --- 3. Drop tabela legada grade_rascunhos ---
    if _has_table(bind, 'grade_rascunhos'):
        op.drop_table('grade_rascunhos')

    # --- 4. Drop índices legados de class_reports ---
    if _has_index(bind, 'class_reports', 'idx_class_reports_habilidades'):
        op.drop_index('idx_class_reports_habilidades', table_name='class_reports',
                      postgresql_where='(bncc_habilidades IS NOT NULL)')
    if _has_index(bind, 'class_reports', 'uq_class_report_turma_data_horario'):
        op.drop_index('uq_class_report_turma_data_horario', table_name='class_reports',
                      postgresql_where='(is_deleted = false)')

    # --- 5. Adicionar novas colunas em grades ---
    if not _has_column(bind, 'grades', 'grade_versao_id'):
        op.add_column('grades', sa.Column('grade_versao_id', sa.Integer(), nullable=True))
    if not _has_column(bind, 'grades', 'slot_horario_id'):
        op.add_column('grades', sa.Column('slot_horario_id', sa.Integer(), nullable=True))
    if not _has_column(bind, 'grades', 'estudio_id'):
        op.add_column('grades', sa.Column('estudio_id', sa.Integer(), nullable=True))
    if not _has_column(bind, 'grades', 'canal_iptv_id'):
        op.add_column('grades', sa.Column('canal_iptv_id', sa.Integer(), nullable=True))
    if not _has_column(bind, 'grades', 'tipo_slot'):
        op.add_column('grades', sa.Column('tipo_slot', sa.String(length=20),
                                           nullable=False, server_default='aula'))

    # --- 6. Converter dia_semana: VARCHAR → INTEGER (apenas se ainda for varchar) ---
    cols = {c["name"]: c for c in sa.inspect(bind).get_columns('grades')}
    dia_col = cols.get('dia_semana')
    dia_is_varchar = dia_col is not None and hasattr(dia_col['type'], 'length')

    if dia_is_varchar:
        if not _has_column(bind, 'grades', 'dia_semana_int'):
            op.add_column('grades', sa.Column('dia_semana_int', sa.Integer(), nullable=True))
        op.execute("""
            UPDATE grades SET dia_semana_int = CASE
                WHEN UPPER(CAST(dia_semana AS TEXT)) IN ('SEGUNDA','SEG','MONDAY') THEN 0
                WHEN UPPER(CAST(dia_semana AS TEXT)) IN ('TERÇA','TERCA','TER','TUESDAY') THEN 1
                WHEN UPPER(CAST(dia_semana AS TEXT)) IN ('QUARTA','QUA','WEDNESDAY') THEN 2
                WHEN UPPER(CAST(dia_semana AS TEXT)) IN ('QUINTA','QUI','THURSDAY') THEN 3
                WHEN UPPER(CAST(dia_semana AS TEXT)) IN ('SEXTA','SEX','FRIDAY') THEN 4
                WHEN UPPER(CAST(dia_semana AS TEXT)) IN ('SÁBADO','SABADO','SAB','SATURDAY') THEN 5
                WHEN UPPER(CAST(dia_semana AS TEXT)) IN ('DOMINGO','DOM','SUNDAY') THEN 6
                ELSE 0
            END
        """)
        op.drop_column('grades', 'dia_semana')
        op.alter_column('grades', 'dia_semana_int',
                        new_column_name='dia_semana',
                        nullable=False,
                        server_default='0')
    elif dia_col is None:
        # Coluna não existe ainda (estado inesperado) — criar como integer
        op.add_column('grades', sa.Column('dia_semana', sa.Integer(),
                                           nullable=False, server_default='0'))

    # --- 7. Ajustar turno_aula para nullable ---
    turno_col = cols.get('turno_aula')
    if turno_col is not None and not turno_col.get('nullable', True):
        op.alter_column('grades', 'turno_aula',
                        existing_type=sa.VARCHAR(length=20),
                        nullable=True)

    # --- 8. Criar FKs em grades (apenas se não existirem) ---
    existing_fks = {fk['constrained_columns'][0]
                    for fk in sa.inspect(bind).get_foreign_keys('grades')}
    if 'grade_versao_id' not in existing_fks and _has_column(bind, 'grades', 'grade_versao_id'):
        op.create_foreign_key(None, 'grades', 'grade_versao', ['grade_versao_id'], ['id'])
    if 'slot_horario_id' not in existing_fks and _has_column(bind, 'grades', 'slot_horario_id'):
        op.create_foreign_key(None, 'grades', 'slot_horario', ['slot_horario_id'], ['id'])
    if 'canal_iptv_id' not in existing_fks and _has_column(bind, 'grades', 'canal_iptv_id'):
        op.create_foreign_key(None, 'grades', 'canal_iptv', ['canal_iptv_id'], ['id'])
    if 'estudio_id' not in existing_fks and _has_column(bind, 'grades', 'estudio_id'):
        op.create_foreign_key(None, 'grades', 'estudio', ['estudio_id'], ['id'])

    # --- 9. Seed: GradeVersao ativa para turmas que já têm grades ---
    op.execute("""
        INSERT INTO grade_versao (turma_id, is_active, data_ativacao, data_criacao)
        SELECT DISTINCT g.turma_id, true, NOW(), NOW()
        FROM grades g
        WHERE g.turma_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM grade_versao gv
              WHERE gv.turma_id = g.turma_id
          )
    """)
    op.execute("""
        UPDATE grades g
        SET grade_versao_id = gv.id
        FROM grade_versao gv
        WHERE gv.turma_id = g.turma_id
          AND gv.is_active = true
          AND g.grade_versao_id IS NULL
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Reverter FK de grade_versao_id (seed)
    op.execute("UPDATE grades SET grade_versao_id = NULL")

    # drop_constraint skipped (name unknown) — FKs para grade_versao, slot_horario, canal_iptv, estudio
    # op.drop_constraint(<name>, 'grades', type_='foreignkey')  # grade_versao_id
    # op.drop_constraint(<name>, 'grades', type_='foreignkey')  # slot_horario_id
    # op.drop_constraint(<name>, 'grades', type_='foreignkey')  # canal_iptv_id
    # op.drop_constraint(<name>, 'grades', type_='foreignkey')  # estudio_id

    op.alter_column('grades', 'turno_aula',
                    existing_type=sa.VARCHAR(length=20),
                    nullable=False)

    # Reverter dia_semana: INTEGER → VARCHAR
    op.add_column('grades', sa.Column('dia_semana_str', sa.VARCHAR(length=20), nullable=True))
    op.execute("""
        UPDATE grades SET dia_semana_str = CASE dia_semana
            WHEN 0 THEN 'SEGUNDA'
            WHEN 1 THEN 'TERÇA'
            WHEN 2 THEN 'QUARTA'
            WHEN 3 THEN 'QUINTA'
            WHEN 4 THEN 'SEXTA'
            WHEN 5 THEN 'SÁBADO'
            WHEN 6 THEN 'DOMINGO'
            ELSE 'SEGUNDA'
        END
    """)
    op.drop_column('grades', 'dia_semana')
    op.alter_column('grades', 'dia_semana_str',
                    new_column_name='dia_semana',
                    nullable=False)

    op.drop_column('grades', 'tipo_slot')
    op.drop_column('grades', 'canal_iptv_id')
    op.drop_column('grades', 'estudio_id')
    op.drop_column('grades', 'slot_horario_id')
    op.drop_column('grades', 'grade_versao_id')

    op.create_index(op.f('uq_class_report_turma_data_horario'), 'class_reports', ['turma_id', 'data_aula', 'horario_aula', 'disciplina_id'], unique=True, postgresql_where='(is_deleted = false)')
    op.create_index(op.f('idx_class_reports_habilidades'), 'class_reports', ['bncc_habilidades'], unique=False, postgresql_where='(bncc_habilidades IS NOT NULL)')

    op.create_table('grade_rascunhos',
        sa.Column('id', sa.UUID(), autoincrement=False, nullable=False),
        sa.Column('upload_batch_id', sa.UUID(), autoincrement=False, nullable=True),
        sa.Column('created_at', sa.DATE(), autoincrement=False, nullable=True),
        sa.Column('serie_origem', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
        sa.Column('materia_origem', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
        sa.Column('professor_origem', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
        sa.Column('turma_id', sa.UUID(), autoincrement=False, nullable=True),
        sa.Column('disciplina_id', sa.UUID(), autoincrement=False, nullable=True),
        sa.Column('professor_id', sa.UUID(), autoincrement=False, nullable=True),
        sa.Column('dia_semana', sa.VARCHAR(length=20), autoincrement=False, nullable=True),
        sa.Column('horario_inicio', postgresql.TIME(), autoincrement=False, nullable=True),
        sa.Column('horario_fim', postgresql.TIME(), autoincrement=False, nullable=True),
        sa.Column('turno_aula', sa.VARCHAR(length=20), autoincrement=False, nullable=True),
        sa.Column('canal_iptv', sa.INTEGER(), autoincrement=False, nullable=True),
        sa.Column('estudio', sa.VARCHAR(length=100), autoincrement=False, nullable=True),
        sa.Column('url_iptv', sa.VARCHAR(length=500), autoincrement=False, nullable=True),
        sa.ForeignKeyConstraint(['disciplina_id'], ['disciplinas.id'], name=op.f('grade_rascunhos_disciplina_id_fkey')),
        sa.ForeignKeyConstraint(['professor_id'], ['professores.id'], name=op.f('grade_rascunhos_professor_id_fkey')),
        sa.ForeignKeyConstraint(['turma_id'], ['turmas.id'], name=op.f('grade_rascunhos_turma_id_fkey')),
        sa.PrimaryKeyConstraint('id', name=op.f('grade_rascunhos_pkey'))
    )

    op.drop_table('grade_versao')
    op.drop_table('slot_horario')
    op.drop_table('estudio')
    op.drop_table('canal_iptv')
