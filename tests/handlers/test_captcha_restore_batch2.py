from unittest.mock import AsyncMock, MagicMock

from aiogram.exceptions import TelegramNetworkError

from app.bot.handlers.captcha import _handle_success
from tests.factories import create_chat, create_user
from tests.handlers.test_captcha_ephemeral import (
    CHAT_ID,
    USER_ID,
    _make_callback,
    _make_i18n,
    _make_mock_bot,
    _seed_session,
)


async def test_emoji_restore_failure_queues_retry_and_still_cleans_messages(db_session, monkeypatch):
    await create_chat(db_session, id=CHAT_ID)
    await create_user(db_session, id=USER_ID)
    captcha = await _seed_session(db_session, message_id=101, ephemeral_message_id=102)
    bot = _make_mock_bot()
    bot.restrict_chat_member.side_effect = TelegramNetworkError(method=MagicMock(), message="Offline")
    publish = AsyncMock()
    monkeypatch.setattr("app.bot.handlers.captcha.bot", bot)
    monkeypatch.setattr("app.core.safe_telegram.broker.publish", publish)
    monkeypatch.setattr("app.bot.handlers.captcha.schedule_autodelete", AsyncMock())

    await _handle_success(_make_callback(), db_session, _make_i18n())

    assert publish.await_args.kwargs["routing_key"] == "q.captcha.restore"
    assert publish.await_args.kwargs["message"]["session_id"] == captcha.id
    bot.delete_message.assert_awaited_once()
    bot.delete_ephemeral_message.assert_awaited_once()


async def test_restore_worker_retries_then_stops_at_limit(db_session, monkeypatch):
    from app.db.models.captcha_session import CaptchaSessionStatus
    from app.worker.captcha import restore_verified_user

    await create_chat(db_session, id=CHAT_ID)
    await create_user(db_session, id=USER_ID)
    captcha = await _seed_session(db_session, status=CaptchaSessionStatus.PASSED)
    bot = _make_mock_bot()
    publish = AsyncMock()
    monkeypatch.setattr("app.worker.captcha.bot", bot)
    monkeypatch.setattr("app.core.safe_telegram.broker.publish", publish)

    await restore_verified_user(CHAT_ID, USER_ID, captcha.id, attempt=2)
    bot.restrict_chat_member.assert_awaited_once()
    publish.assert_not_awaited()

    bot.restrict_chat_member.side_effect = TelegramNetworkError(method=MagicMock(), message="Offline")
    await restore_verified_user(CHAT_ID, USER_ID, captcha.id, attempt=5)
    publish.assert_not_awaited()
