"""normalize existing trigger keys nfkc

Revision ID: 88bc1cf0bd48
Revises: c3d4e5f6a7b8
Create Date: 2026-06-03 14:22:33.662678

"""
import unicodedata
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '88bc1cf0bd48'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CHUNK_SIZE = 500


def upgrade() -> None:
    """NFKC-нормализация key_phrase у всех существующих триггеров.

    Обрабатывается чанками по CHUNK_SIZE, чтобы ограничить размер batch
    UPDATE'а и потребление памяти при большом количестве триггеров.
    Каждый чанк UPDATE'ит только те строки, у которых ключ реально
    меняется (`normalized != key_phrase`).
    """
    conn = op.get_bind()
    offset = 0
    updated_total = 0
    while True:
        rows = conn.execute(
            sa.text(
                "SELECT id, key_phrase FROM triggers ORDER BY id "
                "LIMIT :limit OFFSET :offset"
            ),
            {"limit": CHUNK_SIZE, "offset": offset},
        ).fetchall()
        if not rows:
            break

        to_update = []
        for tid, key in rows:
            normalized = unicodedata.normalize("NFKC", key)
            if normalized != key:
                to_update.append({"k": normalized, "id": tid})

        if to_update:
            conn.execute(
                sa.text("UPDATE triggers SET key_phrase = :k WHERE id = :id"),
                to_update,
            )
            updated_total += len(to_update)

        offset += CHUNK_SIZE

    print(f"[migration] NFKC-normalized {updated_total} trigger keys")


def downgrade() -> None:
    """NFKC деструктивен (compat-формы схлопываются), обратно не вернёшь."""
    pass
