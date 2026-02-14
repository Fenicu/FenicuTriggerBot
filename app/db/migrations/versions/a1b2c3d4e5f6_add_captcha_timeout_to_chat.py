"""add_captcha_timeout_to_chat

Revision ID: a1b2c3d4e5f6
Revises: 89610f0651e5
Create Date: 2026-02-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '89610f0651e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('chats', sa.Column('captcha_timeout', sa.Integer(), server_default='300', nullable=False))


def downgrade() -> None:
    op.drop_column('chats', 'captcha_timeout')
