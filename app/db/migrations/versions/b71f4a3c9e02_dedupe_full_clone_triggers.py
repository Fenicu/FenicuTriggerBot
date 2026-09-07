"""dedupe full clone triggers and forbid new ones

Revision ID: b71f4a3c9e02
Revises: 438c69158379
Create Date: 2026-09-08 01:20:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b71f4a3c9e02"
down_revision: Union[str, Sequence[str], None] = "438c69158379"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Полный клон -- триггер, который сработает на то же и ответит тем же:
# совпадают чат, ключ, тип совпадения, чувствительность к регистру и контент.
# Несколько триггеров с одним ключом, но разным содержимым -- намеренная фича,
# их не трогаем.
_CLONE_KEY = "chat_id, key_phrase, match_type, is_case_sensitive, md5(content::text)"


def upgrade() -> None:
    """Upgrade schema.

    Помечает удалёнными все копии полных клонов, кроме самой ранней, и запрещает
    появление новых уникальным индексом. Удаление мягкое (is_deleted), чтобы
    ошибочно схлопнутое можно было вернуть.
    """
    op.execute(
        f"""
        WITH ranked AS (
            SELECT id,
                   row_number() OVER (PARTITION BY {_CLONE_KEY} ORDER BY id) AS rn
            FROM triggers
            WHERE NOT is_deleted
        )
        UPDATE triggers t
        SET is_deleted = true,
            deleted_at = now()
        FROM ranked r
        WHERE t.id = r.id AND r.rn > 1
        """
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX uq_triggers_no_full_clone
        ON triggers ({_CLONE_KEY})
        WHERE NOT is_deleted
        """
    )


def downgrade() -> None:
    """Downgrade schema.

    Снимает запрет. Схлопнутые клоны не восстанавливаются: какие именно строки
    были погашены этой миграцией, после отката не отличить от удалённых вручную.
    """
    op.execute("DROP INDEX IF EXISTS uq_triggers_no_full_clone")
