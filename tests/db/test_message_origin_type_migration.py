"""
Тест миграции 718722086b5e (restore message origin type):
проставляет дискриминатор `type` у forward_origin / external_reply.origin
в triggers.content и chats.welcome_message, потерянный из-за exclude_defaults.

Поднимает одноразовую БД trigger_migr_test_origin на том же Postgres, DSN из TEST_DATABASE_URL.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest
from aiogram.types import Message
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

REPO_ROOT = Path(__file__).resolve().parents[2]

_test_db_url = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/trigger_test",
)
_url = make_url(_test_db_url).set(drivername="postgresql")
ADMIN_URL = _url.set(database="postgres").render_as_string(hide_password=False)
MIGR_DB = "trigger_migr_test_origin"
MIGR_URL = _url.set(database=MIGR_DB).render_as_string(hide_password=False)

PREVIOUS_REVISION = "b71f4a3c9e02"
NEW_REVISION = "718722086b5e"

CHAT_ID = -100500
_DATE = 1_700_000_000
_BASE = {"message_id": 1, "date": _DATE, "chat": {"id": CHAT_ID, "type": "supergroup"}, "text": "hi"}

# Origin без `type` -- как его сохранял exclude_defaults
BROKEN = {
    "user": {"date": _DATE, "sender_user": {"id": 1, "is_bot": False, "first_name": "A"}},
    "hidden_user": {"date": _DATE, "sender_user_name": "Hidden"},
    "chat": {"date": _DATE, "sender_chat": {"id": -100222, "type": "supergroup", "title": "G"}},
    "channel": {"date": _DATE, "chat": {"id": -100333, "type": "channel", "title": "C"}, "message_id": 7},
}


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


def _insert_trigger(conn, key: str, content: dict) -> int:
    return conn.execute(
        text(
            "INSERT INTO triggers (chat_id, key_phrase, content, match_type, access_level) "
            "VALUES (:chat, :key, CAST(:content AS jsonb), 'EXACT', 'ALL') RETURNING id"
        ),
        {"chat": CHAT_ID, "key": key, "content": json.dumps(content)},
    ).scalar_one()


def _content(conn, trigger_id: int) -> dict:
    return conn.execute(text("SELECT content FROM triggers WHERE id = :id"), {"id": trigger_id}).scalar_one()


def _is_deleted(conn, trigger_id: int) -> bool:
    return conn.execute(text("SELECT is_deleted FROM triggers WHERE id = :id"), {"id": trigger_id}).scalar_one()


def test_upgrade_restores_origin_type_in_triggers(engine):
    with engine.begin() as conn:
        ids = {}
        for origin_type, origin in BROKEN.items():
            ids[("fwd", origin_type)] = _insert_trigger(conn, f"fwd-{origin_type}", {**_BASE, "forward_origin": origin})
            ids[("ext", origin_type)] = _insert_trigger(
                conn, f"ext-{origin_type}", {**_BASE, "external_reply": {"origin": origin}}
            )
            ids[("reply", origin_type)] = _insert_trigger(
                conn, f"reply-{origin_type}", {**_BASE, "reply_to_message": {**_BASE, "forward_origin": origin}}
            )
        null_id = _insert_trigger(conn, "null", {**_BASE, "forward_origin": None})
        plain_id = _insert_trigger(conn, "plain", _BASE)

    _alembic("upgrade", NEW_REVISION)

    with engine.begin() as conn:
        for (kind, origin_type), tid in ids.items():
            msg = Message.model_validate(_content(conn, tid))
            if kind == "fwd":
                origin = msg.forward_origin
            elif kind == "ext":
                origin = msg.external_reply.origin
            else:
                origin = msg.reply_to_message.forward_origin
            assert origin.type == origin_type, (kind, origin_type)
        assert _content(conn, null_id)["forward_origin"] is None
        assert _content(conn, plain_id) == _BASE


def test_upgrade_restores_origin_type_in_welcome(engine):
    welcome = {**_BASE, "forward_origin": BROKEN["channel"], "external_reply": {"origin": BROKEN["hidden_user"]}}
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE chats SET welcome_message = CAST(:w AS jsonb) WHERE id = :id"),
            {"w": json.dumps(welcome), "id": CHAT_ID},
        )

    _alembic("upgrade", NEW_REVISION)

    with engine.begin() as conn:
        stored = conn.execute(text("SELECT welcome_message FROM chats WHERE id = :id"), {"id": CHAT_ID}).scalar_one()
    msg = Message.model_validate(stored)
    assert msg.forward_origin.type == "channel"
    assert msg.external_reply.origin.type == "hidden_user"


def test_upgrade_soft_deletes_clone_that_appears_after_fix(engine):
    """Старый триггер с type и новый без него становятся полными клонами -- поздний гасится."""
    typed = {**_BASE, "forward_origin": {**BROKEN["user"], "type": "user"}}
    broken = {**_BASE, "forward_origin": BROKEN["user"]}
    with engine.begin() as conn:
        old_id = _insert_trigger(conn, "dup", typed)
        new_id = _insert_trigger(conn, "dup", broken)

    _alembic("upgrade", NEW_REVISION)

    with engine.begin() as conn:
        assert not _is_deleted(conn, old_id)
        assert _is_deleted(conn, new_id)
        assert _content(conn, new_id) == typed


def test_upgrade_is_idempotent(engine):
    with engine.begin() as conn:
        tid = _insert_trigger(conn, "fwd", {**_BASE, "forward_origin": BROKEN["chat"]})

    _alembic("upgrade", NEW_REVISION)
    with engine.begin() as conn:
        first = _content(conn, tid)

    _alembic("downgrade", PREVIOUS_REVISION)
    _alembic("upgrade", NEW_REVISION)

    with engine.begin() as conn:
        assert _content(conn, tid) == first
        assert first["forward_origin"]["type"] == "chat"
