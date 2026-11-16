from datetime import UTC, datetime

from sqlalchemy import create_engine, text

from tests.db.test_captcha_migration import _alembic, migr_db  # noqa: F401


def test_chat_pass_migration_backfills_earliest_success_per_chat(migr_db):
    _alembic("upgrade", "718722086b5e")
    engine = create_engine(migr_db)
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO chats (id) VALUES (-10), (-20), (-30)"))
            conn.execute(text("INSERT INTO users (id, has_passed_captcha) VALUES (10, true), (20, true)"))
            conn.execute(text("INSERT INTO user_chats (user_id, chat_id) VALUES (10, -10), (10, -30), (20, -10)"))
            conn.execute(
                text("""
                INSERT INTO chat_captcha_sessions (user_id, chat_id, token, status, created_at, expires_at)
                VALUES (10, -10, 'a', 'passed', '2025-01-02Z', now()),
                       (10, -10, 'b', 'approved', '2025-01-01Z', now()),
                       (10, -20, 'c', 'passed', '2025-01-03Z', now()),
                       (10, -30, 'd', 'pending', '2025-01-01Z', now())
            """)
            )
        _alembic("upgrade", "head")
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT user_id, chat_id, captcha_passed_at FROM user_chats")).all()
        markers = {(u, c): passed for u, c, passed in rows}
        assert markers[10, -10] == datetime(2025, 1, 1, tzinfo=UTC)
        assert markers[10, -20] == datetime(2025, 1, 3, tzinfo=UTC)
        assert markers[10, -30] is None
        assert markers[20, -10] is None
    finally:
        engine.dispose()
