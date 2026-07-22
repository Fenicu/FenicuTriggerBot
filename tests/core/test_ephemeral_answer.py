"""Tests for app/core/safe_telegram.ephemeral_answer."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import Chat, Message, ReplyParameters, User
from app.core.safe_telegram import ephemeral_answer

GROUP_CHAT_ID = -100500
USER_ID = 42


def _bad_request(text: str = "Bad Request: BOT_NOT_ADMIN") -> TelegramBadRequest:
    return TelegramBadRequest(method=MagicMock(), message=text)


def _forbidden(text: str = "Forbidden: bot can't initiate conversation with a user") -> TelegramForbiddenError:
    return TelegramForbiddenError(method=MagicMock(), message=text)


def _message(*, chat_type: str = "supergroup", ephemeral_message_id: int | None = None) -> Message:
    return Message(
        message_id=1,
        date=0,
        chat=Chat(id=GROUP_CHAT_ID, type=chat_type),
        from_user=User(id=USER_ID, is_bot=False, first_name="Test"),
        text="/status",
        ephemeral_message_id=ephemeral_message_id,
    )


@pytest.fixture(autouse=True)
def _allow_send(monkeypatch):
    """safe_send_message проверяет кэш прав через valkey -- в юнит-тестах не нужен."""
    monkeypatch.setattr("app.core.safe_telegram.permissions.is_missing", AsyncMock(return_value=False))


async def test_private_chat_sends_directly():
    """В ЛС -- обычная отправка без receiver_user_id и без reply_parameters."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock())
    message = _message(chat_type="private")

    result = await ephemeral_answer(bot, message, "hello")

    bot.send_message.assert_awaited_once_with(chat_id=GROUP_CHAT_ID, text="hello")
    assert result is bot.send_message.return_value


async def test_ephemeral_command_replies_with_ephemeral_reference():
    """Входящая команда сама эфемерная -> ReplyParameters(ephemeral_message_id=...) + receiver_user_id."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock())
    message = _message(ephemeral_message_id=777)

    result = await ephemeral_answer(bot, message, "hello")

    bot.send_message.assert_awaited_once()
    _, kwargs = bot.send_message.await_args
    assert kwargs["chat_id"] == GROUP_CHAT_ID
    assert kwargs["text"] == "hello"
    assert kwargs["receiver_user_id"] == USER_ID
    assert kwargs["reply_parameters"] == ReplyParameters(ephemeral_message_id=777)
    assert result is bot.send_message.return_value


async def test_group_message_sends_with_receiver_user_id():
    """Обычная команда в группе -> receiver_user_id, без reply_parameters."""
    bot = MagicMock()
    bot.send_message = AsyncMock(return_value=MagicMock())
    message = _message()

    result = await ephemeral_answer(bot, message, "hello")

    bot.send_message.assert_awaited_once()
    _, kwargs = bot.send_message.await_args
    assert kwargs["chat_id"] == GROUP_CHAT_ID
    assert kwargs["receiver_user_id"] == USER_ID
    assert kwargs.get("reply_parameters") is None
    assert result is bot.send_message.return_value


async def test_fallback_sensitive_false_posts_publicly(monkeypatch):
    """sensitive=False, эфемерная отправка упала -> публично сам text через safe_send_message."""
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=_bad_request())
    public_message = MagicMock(message_id=555)
    mock_safe_send = AsyncMock(return_value=public_message)
    monkeypatch.setattr("app.core.safe_telegram.safe_send_message", mock_safe_send)
    message = _message()

    result = await ephemeral_answer(bot, message, "hello", sensitive=False)

    mock_safe_send.assert_awaited_once_with(bot, GROUP_CHAT_ID, text="hello")
    assert result is public_message


async def test_fallback_sensitive_true_dm_succeeds():
    """sensitive=True, эфемерная отправка упала, но ЛС юзеру проходит -> вернуть DM-сообщение."""
    bot = MagicMock()
    dm_message = MagicMock()

    async def _send(*, chat_id, text, **_kwargs):
        if chat_id == GROUP_CHAT_ID:
            raise _bad_request()
        assert chat_id == USER_ID
        return dm_message

    bot.send_message = AsyncMock(side_effect=_send)
    message = _message()

    result = await ephemeral_answer(bot, message, "hello", sensitive=True)

    assert result is dm_message


async def test_sensitive_dm_forbidden_posts_neutral_notice(monkeypatch):
    """Эфемерный send упал, ЛС Forbidden -> публично уходит fallback_notice, НЕ text."""
    bot = MagicMock()

    async def _send(*, chat_id, text, **_kwargs):
        raise _forbidden() if chat_id == USER_ID else _bad_request()

    bot.send_message = AsyncMock(side_effect=_send)
    public_message = MagicMock(message_id=555)
    mock_safe_send = AsyncMock(return_value=public_message)
    monkeypatch.setattr("app.core.safe_telegram.safe_send_message", mock_safe_send)
    message = _message()

    result = await ephemeral_answer(
        bot, message, "sensitive text", sensitive=True, fallback_notice="Ответ отправлен в личные сообщения"
    )

    mock_safe_send.assert_awaited_once_with(bot, GROUP_CHAT_ID, text="Ответ отправлен в личные сообщения")
    assert result is None


async def test_public_fallback_schedules_autodelete(monkeypatch):
    """sensitive=False fallback -> schedule_autodelete(chat_id, msg_id, settings, msg_type)."""
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=_bad_request())
    public_message = MagicMock(message_id=555)
    mock_safe_send = AsyncMock(return_value=public_message)
    mock_schedule = AsyncMock()
    monkeypatch.setattr("app.core.safe_telegram.safe_send_message", mock_safe_send)
    monkeypatch.setattr("app.core.safe_telegram.schedule_autodelete", mock_schedule)
    message = _message()
    autodelete_settings = {"command_reply": {"enabled": True, "delay": 15}}

    result = await ephemeral_answer(
        bot, message, "hello", sensitive=False, autodelete=(autodelete_settings, "command_reply")
    )

    mock_schedule.assert_awaited_once_with(GROUP_CHAT_ID, 555, autodelete_settings, "command_reply")
    assert result is public_message


async def test_public_fallback_forwards_parse_mode_strips_reply_markup(monkeypatch):
    """sensitive=False fallback: parse_mode долетает до safe_send_message, reply_markup вырезан."""
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=_bad_request())
    mock_safe_send = AsyncMock(return_value=MagicMock(message_id=555))
    monkeypatch.setattr("app.core.safe_telegram.safe_send_message", mock_safe_send)
    message = _message()
    markup = MagicMock()

    await ephemeral_answer(bot, message, "hello", sensitive=False, parse_mode="HTML", reply_markup=markup)

    mock_safe_send.assert_awaited_once_with(bot, GROUP_CHAT_ID, text="hello", parse_mode="HTML")


async def test_notice_fallback_forwards_parse_mode_strips_reply_markup(monkeypatch):
    """sensitive=True, ЛС Forbidden: notice-fallback тоже получает parse_mode, но не reply_markup."""
    bot = MagicMock()

    async def _send(*, chat_id, text, **_kwargs):
        raise _forbidden() if chat_id == USER_ID else _bad_request()

    bot.send_message = AsyncMock(side_effect=_send)
    mock_safe_send = AsyncMock(return_value=MagicMock(message_id=555))
    monkeypatch.setattr("app.core.safe_telegram.safe_send_message", mock_safe_send)
    message = _message()
    markup = MagicMock()

    await ephemeral_answer(
        bot,
        message,
        "sensitive text",
        sensitive=True,
        fallback_notice="Ответ отправлен в личные сообщения",
        parse_mode="HTML",
        reply_markup=markup,
    )

    mock_safe_send.assert_awaited_once_with(
        bot, GROUP_CHAT_ID, text="Ответ отправлен в личные сообщения", parse_mode="HTML"
    )


async def test_public_fallback_no_autodelete_when_send_fails(monkeypatch):
    """safe_send_message вернул None (право закэшировано отсутствующим) -> schedule_autodelete не зовётся."""
    bot = MagicMock()
    bot.send_message = AsyncMock(side_effect=_bad_request())
    mock_safe_send = AsyncMock(return_value=None)
    mock_schedule = AsyncMock()
    monkeypatch.setattr("app.core.safe_telegram.safe_send_message", mock_safe_send)
    monkeypatch.setattr("app.core.safe_telegram.schedule_autodelete", mock_schedule)
    message = _message()
    autodelete_settings = {"command_reply": {"enabled": True, "delay": 15}}

    result = await ephemeral_answer(
        bot, message, "hello", sensitive=False, autodelete=(autodelete_settings, "command_reply")
    )

    mock_schedule.assert_not_awaited()
    assert result is None
