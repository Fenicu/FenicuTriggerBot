"""add rich to trigger

Revision ID: d1e2f3a4b5c6
Revises: 88bc1cf0bd48
Create Date: 2026-06-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = '88bc1cf0bd48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('triggers', sa.Column('rich', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('triggers', 'rich')
