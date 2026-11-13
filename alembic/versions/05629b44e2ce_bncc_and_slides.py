"""bncc_and_slides

Revision ID: 05629b44e2ce
Revises: 4fbc82998e83
Create Date: 2026-04-16 19:19:07.842435

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
"""bncc_and_slides

Revision ID: 05629b44e2ce
Revises: 4fbc82998e83
Create Date: 2026-04-16 19:19:07.842435

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '05629b44e2ce'
down_revision: Union[str, Sequence[str], None] = '4fbc82998e83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('class_reports', sa.Column('bncc_habilidades', sa.JSON(), nullable=True))
    op.add_column('class_reports', sa.Column('slide_link', sa.String(length=1000), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('class_reports', 'slide_link')
    op.drop_column('class_reports', 'bncc_habilidades')

    # ### end Alembic commands ###
