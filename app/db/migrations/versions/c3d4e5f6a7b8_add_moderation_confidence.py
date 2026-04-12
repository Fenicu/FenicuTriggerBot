"""add moderation_category and moderation_confidence to triggers

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-04-13 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('triggers', sa.Column('moderation_category', sa.Text(), nullable=True))
    op.add_column('triggers', sa.Column('moderation_confidence', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('triggers', 'moderation_confidence')
    op.drop_column('triggers', 'moderation_category')
