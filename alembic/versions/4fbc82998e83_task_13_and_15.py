"""Task 13: Change minutos_atraso to HH:MM and Task 15: Add is_active columns

Revision ID: 4fbc82998e83
Revises: cdc3eda23599
Create Date: 2026-04-14 16:47:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4fbc82998e83'
down_revision = 'cdc3eda23599'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── TASK 15: Adicionar is_active para Soft Delete ───
    op.add_column('professores', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('disciplinas', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('diretores_imagem', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False))

    # ─── TASK 13: Alterar minutos_atraso para String(5) (HH:MM) ───
    # No PostgreSQL, fazemos a conversão de Integer minutos para String "HH:MM"
    op.execute("""
        ALTER TABLE class_reports 
        ALTER COLUMN minutos_atraso TYPE VARCHAR(5) 
        USING (
            CASE 
                WHEN minutos_atraso IS NULL THEN NULL
                ELSE LPAD((minutos_atraso / 60)::text, 2, '0') || ':' || LPAD((minutos_atraso % 60)::text, 2, '0')
            END
        )
    """)


def downgrade() -> None:
    # Reverter minutos_atraso para Integer (tentativa de conversão)
    op.execute("""
        ALTER TABLE class_reports 
        ALTER COLUMN minutos_atraso TYPE INTEGER 
        USING (
            CASE 
                WHEN minutos_atraso IS NULL THEN NULL
                WHEN minutos_atraso ~ '^[0-9]{2}:[0-9]{2}$' THEN 
                    (split_part(minutos_atraso, ':', 1)::integer * 60) + split_part(minutos_atraso, ':', 2)::integer
                ELSE NULL
            END
        )
    """)
    
    op.drop_column('diretores_imagem', 'is_active')
    op.drop_column('disciplinas', 'is_active')
    op.drop_column('professores', 'is_active')
