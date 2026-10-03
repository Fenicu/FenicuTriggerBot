"""restore message origin type

Revision ID: 718722086b5e
Revises: b71f4a3c9e02
Create Date: 2026-10-03 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "718722086b5e"
down_revision: Union[str, Sequence[str], None] = "b71f4a3c9e02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Сериализация с exclude_defaults выкидывала дискриминатор `type` у MessageOrigin,
# и Message.model_validate падал с union_tag_not_found. Тип однозначно
# восстанавливается по ключу, характерному для каждого варианта.
_ORIGIN_PATHS = (
    "{forward_origin}",
    "{external_reply,origin}",
    "{reply_to_message,forward_origin}",
    "{reply_to_message,external_reply,origin}",
)

_TARGETS = (
    ("triggers", "content"),
    ("chats", "welcome_message"),
)

_CLONE_KEY = "chat_id, key_phrase, match_type, is_case_sensitive, md5(content::text)"


def _restore_type(table: str, column: str, path: str) -> str:
    obj = f"({column} #> '{path}')"
    return f"""
        UPDATE {table}
        SET {column} = jsonb_set(
            {column},
            '{path}',
            {obj} || jsonb_build_object(
                'type',
                CASE
                    WHEN {obj} ? 'sender_user' THEN 'user'
                    WHEN {obj} ? 'sender_user_name' THEN 'hidden_user'
                    WHEN {obj} ? 'sender_chat' THEN 'chat'
                    ELSE 'channel'
                END
            )
        )
        WHERE jsonb_typeof({obj}) = 'object'
          AND NOT {obj} ? 'type'
          AND {obj} ?| array['sender_user', 'sender_user_name', 'sender_chat', 'chat']
    """


def upgrade() -> None:
    """Upgrade schema.

    Проставляет `type` у forward_origin / external_reply.origin (в т.ч. внутри
    reply_to_message) в контенте триггеров и приветствий. Идемпотентна: трогает
    только объекты без `type`.

    Старые триггеры (до exclude_defaults) хранились с `type`, поэтому после
    починки часть новых может стать полным клоном старого. Индекс
    uq_triggers_no_full_clone снимается на время UPDATE, поздние клоны гасятся
    так же, как в b71f4a3c9e02, и индекс создаётся заново.
    """
    op.execute("DROP INDEX IF EXISTS uq_triggers_no_full_clone")

    for table, column in _TARGETS:
        for path in _ORIGIN_PATHS:
            op.execute(_restore_type(table, column, path))

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

    No-op: восстановленный `type` корректен для любой версии кода.
    """
