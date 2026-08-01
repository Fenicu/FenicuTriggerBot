"""
Тест миграции 438c69158379 (add pg_trgm gin indexes for admin search):
upgrade создаёт extension pg_trgm + GIN-индексы (gin_trgm_ops) под ILIKE-поиск
и btree-индекс triggers(created_by); downgrade убирает всё зеркально.

Поднимает одноразовую БД trigger_migr_test_trgm на том же Postgres (суперюзер postgres/postgres),
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

_url = make_url(_test_db_url)
_url = _url.set(drivername="postgresql")

ADMIN_URL = _url.set(database="postgres").render_as_string(hide_password=False)

MIGR_DB = "trigger_migr_test_trgm"
MIGR_URL = _url.set(database=MIGR_DB).render_as_string(hide_password=False)

PREVIOUS_REVISION = "ecbb12839e31"
NEW_REVISION = "438c69158379"

TRGM_INDEXES = [
    ("chats", "ix_chats_title_trgm"),
    ("chats", "ix_chats_username_trgm"),
    ("users", "ix_users_username_trgm"),
    ("users", "ix_users_first_name_trgm"),
    ("users", "ix_users_last_name_trgm"),
    ("triggers", "ix_triggers_key_phrase_trgm"),
]


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
    """Создаёт одноразовую БД trigger_migr_test_trgm, дропает её после теста."""
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


def _extension_exists(engine) -> bool:
    with engine.begin() as conn:
        return bool(conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")).scalar())


def _index_exists(engine, table: str, index: str) -> bool:
    with engine.begin() as conn:
        return bool(
            conn.execute(
                text("SELECT 1 FROM pg_indexes WHERE tablename = :t AND indexname = :i"),
                {"t": table, "i": index},
            ).scalar()
        )


def test_upgrade_creates_trgm_extension_and_indexes(migr_db):
    """upgrade head создаёт pg_trgm и все GIN-индексы + btree под created_by."""
    _alembic("upgrade", PREVIOUS_REVISION)

    engine = create_engine(migr_db)
    assert not _extension_exists(engine)

    _alembic("upgrade", NEW_REVISION)

    assert _extension_exists(engine)
    for table, index in TRGM_INDEXES:
        assert _index_exists(engine, table, index), f"{index} missing on {table}"
    assert _index_exists(engine, "triggers", "ix_triggers_created_by")

    engine.dispose()


def test_downgrade_drops_indexes_and_extension(migr_db):
    """downgrade зеркально убирает все GIN-индексы, btree под created_by и extension."""
    _alembic("upgrade", NEW_REVISION)

    engine = create_engine(migr_db)
    assert _extension_exists(engine)

    _alembic("downgrade", PREVIOUS_REVISION)

    assert not _extension_exists(engine)
    for table, index in TRGM_INDEXES:
        assert not _index_exists(engine, table, index)
    assert not _index_exists(engine, "triggers", "ix_triggers_created_by")

    engine.dispose()


def test_upgrade_downgrade_upgrade_cycle_is_idempotent(migr_db):
    """upgrade -> downgrade -> upgrade проходит без ошибок и восстанавливает всё состояние."""
    _alembic("upgrade", NEW_REVISION)
    _alembic("downgrade", PREVIOUS_REVISION)
    _alembic("upgrade", NEW_REVISION)

    engine = create_engine(migr_db)
    assert _extension_exists(engine)
    for table, index in TRGM_INDEXES:
        assert _index_exists(engine, table, index)
    assert _index_exists(engine, "triggers", "ix_triggers_created_by")

    engine.dispose()
