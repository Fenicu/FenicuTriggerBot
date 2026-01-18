"""add_captcha_type_to_chat

Revision ID: 7c452372538e
Revises: 44535d862490
Create Date: 2026-01-18 23:58:57.447754

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c452372538e'
down_revision: Union[str, Sequence[str], None] = '44535d862490'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('chats', sa.Column('captcha_type', sa.String(), server_default='emoji', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('chats', 'captcha_type')
