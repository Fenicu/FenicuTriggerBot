"""add autodelete_settings and migrate welcome_delete_timeout

Revision ID: a8f1d2e3b4c5
Revises: 7a0344c0ace4
Create Date: 2026-04-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a8f1d2e3b4c5'
down_revision: Union[str, Sequence[str], None] = '7a0344c0ace4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new column
    op.add_column('chats', sa.Column('autodelete_settings', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # 2. Migrate welcome_delete_timeout data
    op.execute("""
        UPDATE chats
        SET autodelete_settings = jsonb_build_object(
            'welcome', jsonb_build_object(
                'enabled', true,
                'delay', LEAST(welcome_delete_timeout, 3600)
            )
        )
        WHERE welcome_delete_timeout > 0
    """)

    # 3. Drop old column
    op.drop_column('chats', 'welcome_delete_timeout')


def downgrade() -> None:
    op.add_column('chats', sa.Column('welcome_delete_timeout', sa.Integer(), server_default='0', nullable=False))

    op.execute("""
        UPDATE chats
        SET welcome_delete_timeout = COALESCE(
            (autodelete_settings->'welcome'->>'delay')::int,
            0
        )
        WHERE autodelete_settings IS NOT NULL
          AND autodelete_settings->'welcome' IS NOT NULL
          AND (autodelete_settings->'welcome'->>'enabled')::boolean = true
    """)

    op.drop_column('chats', 'autodelete_settings')
