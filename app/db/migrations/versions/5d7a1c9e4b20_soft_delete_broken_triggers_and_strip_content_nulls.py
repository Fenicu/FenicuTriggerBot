"""Мягко удали неотправляемые триггеры и убери null-ключи из их content."""

from typing import Sequence, Union

from alembic import op

revision: str = "5d7a1c9e4b20"
down_revision: Union[str, Sequence[str], None] = "c42b8e517d90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Служебные сообщения (new_chat_members / forum_topic_created) и легаси rich_message,
# который больше не парсится: отправить такой триггер невозможно.
BROKEN_TRIGGER_IDS = (23482, 24299, 24300, 24301, 24302, 24385, 15990, 22626, 22749)


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE triggers
        SET is_deleted = true,
            deleted_at = now()
        WHERE id IN ({", ".join(str(trigger_id) for trigger_id in BROKEN_TRIGGER_IDS)})
          AND NOT is_deleted
        """
    )
    # jsonb_strip_nulls убирает только null-ключи объектов (рекурсивно),
    # null-элементы массивов остаются: aiogram разбирает такие content так же.
    op.execute(
        """
        UPDATE triggers
        SET content = jsonb_strip_nulls(content)
        WHERE content <> jsonb_strip_nulls(content)
        """
    )


def downgrade() -> None:
    # Удалённые null-ключи неотличимы от отсутствующих, soft-delete не откатываем.
    pass
