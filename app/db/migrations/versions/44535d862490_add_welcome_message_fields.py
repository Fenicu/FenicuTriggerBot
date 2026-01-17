"""add_welcome_message_fields

Revision ID: 44535d862490
Revises: d7f98928cb5c
Create Date: 2026-01-18 02:26:04.738261

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '44535d862490'
down_revision: Union[str, Sequence[str], None] = 'd7f98928cb5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('chats', sa.Column('welcome_enabled', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('chats', sa.Column('welcome_message', JSONB, nullable=True))
    op.add_column('chats', sa.Column('welcome_delete_timeout', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('chats', 'welcome_delete_timeout')
    op.drop_column('chats', 'welcome_message')
    op.drop_column('chats', 'welcome_enabled')
