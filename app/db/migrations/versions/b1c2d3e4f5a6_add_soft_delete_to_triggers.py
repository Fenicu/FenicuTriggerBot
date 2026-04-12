"""add soft delete to triggers

Revision ID: b1c2d3e4f5a6
Revises: a8f1d2e3b4c5
Create Date: 2026-04-12 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'a8f1d2e3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('triggers', sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('triggers', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_triggers_is_deleted', 'triggers', ['is_deleted'])


def downgrade() -> None:
    op.drop_index('ix_triggers_is_deleted', table_name='triggers')
    op.drop_column('triggers', 'deleted_at')
    op.drop_column('triggers', 'is_deleted')
