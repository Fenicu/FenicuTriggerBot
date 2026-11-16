"""
Тест миграции 5d7a1c9e4b20 (soft_delete_broken_triggers_and_strip_content_nulls):
мягко удаляет неотправляемые триггеры и убирает null-ключи из triggers.content.

Поднимает одноразовую БД trigger_migr_test_nulls на том же Postgres, DSN из TEST_DATABASE_URL.
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

REPO_ROOT = Path(__file__).resolve().parents[2]

_test_db_url = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/trigger_test",
)
_url = make_url(_test_db_url).set(drivername="postgresql")
ADMIN_URL = _url.set(database="postgres").render_as_string(hide_password=False)
MIGR_DB = "trigger_migr_test_nulls"
MIGR_URL = _url.set(database=MIGR_DB).render_as_string(hide_password=False)

PREVIOUS_REVISION = "c42b8e517d90"
NEW_REVISION = "5d7a1c9e4b20"

CHAT_ID = -100500

# Девять сломанных id из миграции: часть вставляем, остальные отсутствуют --
# миграция не должна падать на несуществующих строках.
BROKEN_SERVICE_ID = 23482
BROKEN_SERVICE_OTHER_ID = 24300
BROKEN_RICH_ID = 15990
MISSING_BROKEN_ID = 24385

UNRELATED_ID = 90001
LIVE_ID = 90002

ORIGINAL_DELETED_AT = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)

# Так триггеры выглядели после exclude_defaults: все поля сообщения, часть -- null.
BLOATED = {
    "message_id": 1,
    "date": 1_700_000_000,
    "chat": {"id": CHAT_ID, "type": "supergroup", "title": "Test", "username": None},
    "text": "hello",
    "entities": [
        {"type": "bold", "offset": 0, "length": 5, "url": None, "user": None},
        None,
    ],
    "photo": None,
    "animation": None,
    "reply_to_message": {
        "message_id": 1,
        "date": 1_700_000_000,
        "chat": {"id": CHAT_ID, "type": "supergroup"},
        "text": None,
    },
}

STRIPPED = {
    "message_id": 1,
    "date": 1_700_000_000,
    "chat": {"id": CHAT_ID, "type": "supergroup", "title": "Test"},
    "text": "hello",
    "entities": [
        {"type": "bold", "offset": 0, "length": 5},
        None,
    ],
    "reply_to_message": {
        "message_id": 1,
        "date": 1_700_000_000,
        "chat": {"id": CHAT_ID, "type": "supergroup"},
    },
}

PLAIN = {"message_id": 2, "date": 1_700_000_001, "chat": {"id": CHAT_ID, "type": "supergroup"}, "text": "plain"}


def _alembic(*args: str) -> None:
    env = os.environ.copy()
    env["POSTGRES_URL"] = MIGR_URL
    result = subprocess.run(
        ["uv", "run", "alembic", *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=env,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}"


@pytest.fixture
def engine():
    admin_engine = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{MIGR_DB}"'))
        conn.execute(text(f'CREATE DATABASE "{MIGR_DB}"'))
    admin_engine.dispose()

    _alembic("upgrade", PREVIOUS_REVISION)
    eng = create_engine(MIGR_URL)
    with eng.begin() as conn:
        conn.execute(text("INSERT INTO chats (id) VALUES (:id)"), {"id": CHAT_ID})

    yield eng

    eng.dispose()
    admin_engine = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{MIGR_DB}"'))
    admin_engine.dispose()


def _insert_trigger(
    conn,
    trigger_id: int,
    content: dict,
    *,
    is_deleted: bool = False,
    deleted_at: datetime | None = None,
) -> None:
    conn.execute(
        text(
            "INSERT INTO triggers "
            "(id, chat_id, key_phrase, content, match_type, access_level, is_deleted, deleted_at) "
            "VALUES (:id, :chat, :key, CAST(:content AS jsonb), 'EXACT', 'ALL', :deleted, :deleted_at)"
        ),
        {
            "id": trigger_id,
            "chat": CHAT_ID,
            "key": f"key-{trigger_id}",
            "content": json.dumps(content),
            "deleted": is_deleted,
            "deleted_at": deleted_at,
        },
    )


def _row(conn, trigger_id: int) -> dict:
    return (
        conn.execute(
            text("SELECT content, is_deleted, deleted_at FROM triggers WHERE id = :id"),
            {"id": trigger_id},
        )
        .mappings()
        .one()
    )


def test_upgrade_soft_deletes_broken_triggers(engine):
    with engine.begin() as conn:
        _insert_trigger(conn, BROKEN_SERVICE_ID, PLAIN)
        _insert_trigger(conn, BROKEN_SERVICE_OTHER_ID, PLAIN)
        _insert_trigger(conn, BROKEN_RICH_ID, PLAIN, is_deleted=True, deleted_at=ORIGINAL_DELETED_AT)
        _insert_trigger(conn, UNRELATED_ID, PLAIN)

    _alembic("upgrade", NEW_REVISION)

    with engine.begin() as conn:
        for trigger_id in (BROKEN_SERVICE_ID, BROKEN_SERVICE_OTHER_ID):
            row = _row(conn, trigger_id)
            assert row["is_deleted"] is True
            assert row["deleted_at"] is not None

        already_deleted = _row(conn, BROKEN_RICH_ID)
        assert already_deleted["is_deleted"] is True
        assert already_deleted["deleted_at"] == ORIGINAL_DELETED_AT

        unrelated = _row(conn, UNRELATED_ID)
        assert unrelated["is_deleted"] is False
        assert unrelated["deleted_at"] is None

        assert not conn.execute(
            text("SELECT 1 FROM triggers WHERE id = :id"), {"id": MISSING_BROKEN_ID}
        ).scalar()


def test_upgrade_strips_null_object_keys_but_keeps_null_array_elements(engine):
    with engine.begin() as conn:
        _insert_trigger(conn, LIVE_ID, BLOATED)
        _insert_trigger(conn, UNRELATED_ID, PLAIN)

    _alembic("upgrade", NEW_REVISION)

    with engine.begin() as conn:
        stripped = _row(conn, LIVE_ID)
        assert stripped["content"] == STRIPPED
        assert "photo" not in stripped["content"]
        assert stripped["content"]["entities"][1] is None
        assert stripped["is_deleted"] is False

        plain = _row(conn, UNRELATED_ID)
        assert plain["content"] == PLAIN
        assert plain["is_deleted"] is False
