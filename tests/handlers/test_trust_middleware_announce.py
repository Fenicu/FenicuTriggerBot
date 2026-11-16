"""TrustMiddleware: сбой объявления о доверии не обрывает обработку сообщения."""

from unittest.mock import AsyncMock, MagicMock

from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import Message


def _data(i18n: MagicMock) -> dict:
    return {
        "session": AsyncMock(add=MagicMock()),
        "user": MagicMock(is_trusted=True),
        "db_chat": MagicMock(is_trusted=False),
        "i18n": i18n,
    }


def _message() -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock(id=1, username=None, full_name="Trusted <User>")
    msg.chat = MagicMock(id=-100, type="supergroup")
    return msg


async def test_handler_runs_when_announcement_fails():
    from app.bot.middlewares.trust import TrustMiddleware

    msg = _message()
    msg.answer = AsyncMock(side_effect=TelegramForbiddenError(method=MagicMock(), message="bot was kicked"))
    data = _data(MagicMock())
    handler = AsyncMock(return_value="ok")

    result = await TrustMiddleware()(handler, msg, data)

    assert result == "ok"
    handler.assert_awaited_once()
    assert data["db_chat"].is_trusted is True
    data["session"].commit.assert_awaited_once()


async def test_handler_runs_when_translation_fails():
    from app.bot.middlewares.trust import TrustMiddleware

    msg = _message()
    msg.answer = AsyncMock()
    i18n = MagicMock()
    i18n.chat.became.trusted.side_effect = KeyError("chat-became-trusted")
    handler = AsyncMock(return_value="ok")

    assert await TrustMiddleware()(handler, msg, _data(i18n)) == "ok"
    handler.assert_awaited_once()
