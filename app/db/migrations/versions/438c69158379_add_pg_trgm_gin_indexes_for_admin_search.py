"""add pg_trgm gin indexes for admin search

Revision ID: 438c69158379
Revises: ecbb12839e31
Create Date: 2026-08-01 04:28:39.949377

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '438c69158379'
down_revision: Union[str, Sequence[str], None] = 'ecbb12839e31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    GIN-индексы с gin_trgm_ops ускоряют ILIKE '%...%' в поиске админки (Chat.title/username,
    User.username/first_name/last_name, Trigger.key_phrase) -- существующие btree-индексы
    для запроса с ведущим '%' бесполезны, поиск шёл full scan'ом. btree-индексы намеренно
    не удаляются -- пригодятся для точных сравнений (=).
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_index(
        "ix_chats_title_trgm",
        "chats",
        ["title"],
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_chats_username_trgm",
        "chats",
        ["username"],
        postgresql_using="gin",
        postgresql_ops={"username": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_users_username_trgm",
        "users",
        ["username"],
        postgresql_using="gin",
        postgresql_ops={"username": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_users_first_name_trgm",
        "users",
        ["first_name"],
        postgresql_using="gin",
        postgresql_ops={"first_name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_users_last_name_trgm",
        "users",
        ["last_name"],
        postgresql_using="gin",
        postgresql_ops={"last_name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_triggers_key_phrase_trgm",
        "triggers",
        ["key_phrase"],
        postgresql_using="gin",
        postgresql_ops={"key_phrase": "gin_trgm_ops"},
    )

    # Под новый фильтр created_by (карточка автора триггеров в админке)
    op.create_index("ix_triggers_created_by", "triggers", ["created_by"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_triggers_created_by", table_name="triggers")

    op.drop_index("ix_triggers_key_phrase_trgm", table_name="triggers")
    op.drop_index("ix_users_last_name_trgm", table_name="users")
    op.drop_index("ix_users_first_name_trgm", table_name="users")
    op.drop_index("ix_users_username_trgm", table_name="users")
    op.drop_index("ix_chats_username_trgm", table_name="chats")
    op.drop_index("ix_chats_title_trgm", table_name="chats")

    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
