"""
Тест миграции e7a1b2c3d4f5 (captcha_session_v2): backfill legacy is_completed -> status/token,
downgrade -1 чистит non-legacy строки и восстанавливает is_completed.

Поднимает одноразовую БД trigger_migr_test на том же Postgres (суперюзер postgres/postgres),
DSN производится из TEST_DATABASE_URL, не трогает основную trigger_test сессионную БД из tests/conftest.py.
"""

import os
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

REPO_ROOT = Path(__file__).resolve().parents[2]

# Читаем TEST_DATABASE_URL с тем же дефолтом, что и conftest.py
_test_db_url = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/trigger_test",
)

# Парсим URL и убираем +asyncpg для синхронного подключения
_url = make_url(_test_db_url)
_url = _url.set(drivername="postgresql")

# Производим ADMIN_URL (подключение к postgres БД для администрирования)
ADMIN_URL = _url.set(database="postgres").render_as_string(hide_password=False)

MIGR_DB = "trigger_migr_test"
# Производим MIGR_URL (подключение к миграционной БД)
MIGR_URL = _url.set(database=MIGR_DB).render_as_string(hide_password=False)

OLD_REVISION = "d1e2f3a4b5c6"
TABLE = "chat_captcha_sessions"


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
def migr_db():
    """Создаёт одноразовую БД trigger_migr_test, дропает её после теста."""
    admin_engine = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{MIGR_DB}"'))
        conn.execute(text(f'CREATE DATABASE "{MIGR_DB}"'))
    admin_engine.dispose()

    yield MIGR_URL

    admin_engine = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{MIGR_DB}"'))
    admin_engine.dispose()


def test_upgrade_backfills_status_and_downgrade_cleans_up(migr_db):
    """
    Легаси-строки (is_completed=true/false, message_id=0) переживают upgrade+downgrade
    с восстановленным is_completed; ephemeral/join_request-строки удаляются на downgrade;
    после downgrade оба enum-типа отсутствуют в pg_type.
    """
    _alembic("upgrade", OLD_REVISION)

    engine = create_engine(migr_db)
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO chats (id) VALUES (-100600)"))
        conn.execute(text("INSERT INTO users (id) VALUES (777), (778)"))
        conn.execute(
            text(
                "INSERT INTO chat_captcha_sessions "
                "(chat_id, user_id, message_id, expires_at, is_completed) "
                "VALUES (:chat_id, :user_id, 0, now() + interval '5 minutes', :done)"
            ),
            [
                {"chat_id": -100600, "user_id": 777, "done": True},
                {"chat_id": -100600, "user_id": 778, "done": False},
            ],
        )

    _alembic("upgrade", "head")

    with engine.begin() as conn:
        rows = (
            conn.execute(text(f"SELECT user_id, status, token, message_id FROM {TABLE} ORDER BY user_id"))
            .mappings()
            .all()
        )
    assert [r["user_id"] for r in rows] == [777, 778]
    assert rows[0]["status"] == "passed"
    assert rows[1]["status"] == "pending"
    assert rows[0]["token"] and rows[1]["token"]
    assert rows[0]["token"] != rows[1]["token"]
    assert rows[0]["message_id"] == 0

    # Засеваем non-legacy строки (pending), которые старая схема представить не может.
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id) VALUES (779), (780), (781)"))
        conn.execute(
            text(
                f"INSERT INTO {TABLE} "
                "(chat_id, user_id, ephemeral_message_id, kind, status, expires_at, token) "
                "VALUES (:chat_id, :user_id, 555, 'chat', 'pending', now() + interval '5 minutes', :token)"
            ),
            {"chat_id": -100600, "user_id": 779, "token": "tok-ephemeral"},
        )
        conn.execute(
            text(
                f"INSERT INTO {TABLE} "
                "(chat_id, user_id, kind, status, join_request_query_id, expires_at, token) "
                "VALUES (:chat_id, :user_id, 'join_request', 'pending', :qid, now() + interval '5 minutes', :token)"
            ),
            {"chat_id": -100600, "user_id": 780, "qid": "query-abc", "token": "tok-joinreq"},
        )
        conn.execute(
            text(
                f"INSERT INTO {TABLE} "
                "(chat_id, user_id, message_id, kind, status, join_request_query_id, expires_at, token) "
                "VALUES (:chat_id, :user_id, 123, 'join_request', 'pending', :qid, now() + interval '5 minutes', :token)"
            ),
            {"chat_id": -100600, "user_id": 781, "qid": "q-migr-3", "token": "tok-joinreq-3"},
        )

    _alembic("downgrade", OLD_REVISION)

    with engine.begin() as conn:
        remaining = conn.execute(text(f"SELECT user_id, is_completed FROM {TABLE} ORDER BY user_id")).mappings().all()
        enum_count = conn.execute(text("SELECT count(*) FROM pg_type WHERE typname LIKE 'captcha_session_%'")).scalar()
        message_id_nullable = conn.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                f"WHERE table_name = '{TABLE}' AND column_name = 'message_id'"
            )
        ).scalar()

    # Проверяем, что остались только легаси-строки (777, 778), все три non-legacy (779, 780, 781) удалены.
    assert [r["user_id"] for r in remaining] == [777, 778]
    assert remaining[0]["is_completed"] is True
    assert remaining[1]["is_completed"] is False
    assert enum_count == 0
    assert message_id_nullable == "NO"

    engine.dispose()  # закрыть пул соединений — иначе фикстура не сможет DROP DATABASE
