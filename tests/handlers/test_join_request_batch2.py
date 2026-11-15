from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter, TelegramServerError

from app.bot.handlers.join_request import on_chat_join_request
from app.db.models.captcha_session import CaptchaSessionStatus
from tests.factories import create_chat, create_user
from tests.handlers.test_join_request import _fetch_by_query_id, _make_bot, _make_event


@pytest.mark.parametrize("error_cls", [TelegramForbiddenError, TelegramRetryAfter, TelegramServerError])
async def test_any_telegram_send_failure_compensates(db_session, monkeypatch, error_cls):
    chat = await create_chat(db_session, captcha_enabled=True)
    user = await create_user(db_session)
    await db_session.commit()
    bot = _make_bot()
    extra = {"retry_after": 30} if error_cls is TelegramRetryAfter else {}
    error = error_cls(method=MagicMock(), message="Temporary API failure", **extra)
    bot.send_chat_join_request_web_app.side_effect = error
    monkeypatch.setattr("app.bot.handlers.join_request.bot", bot)

    await on_chat_join_request(_make_event(chat.id, user.id, "q-api-failure"), db_session, chat, user)

    captcha = await _fetch_by_query_id(db_session, "q-api-failure")
    assert captcha.status == CaptchaSessionStatus.EXPIRED
    bot.answer_chat_join_request_query.assert_awaited_once_with(
        chat_join_request_query_id="q-api-failure", result="queue"
    )
