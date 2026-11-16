"""BannedChatMiddleware: кэш отрицательного результата и место в цепочке middleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Update


@pytest.fixture
def middleware():
    from app.bot.middlewares.banned import BannedChatMiddleware

    return BannedChatMiddleware(bot=MagicMock(leave_chat=AsyncMock()))


def _message_event(chat_id: int = -100555) -> MagicMock:
    event = MagicMock(spec=Update)
    event.message = MagicMock()
    event.message.chat.id = chat_id
    event.callback_query = None
    event.my_chat_member = None
    return event


def _session(banned: object | None) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = banned
    session.execute = AsyncMock(return_value=result)
    return session


async def test_not_banned_result_is_cached(middleware):
    session = _session(banned=None)
    handler = AsyncMock(return_value="ok")

    with patch("app.bot.middlewares.banned.valkey") as mock_valkey:
        mock_valkey.get = AsyncMock(return_value=None)
        mock_valkey.set = AsyncMock()
        result = await middleware(handler, _message_event(), {"session": session})

    assert result == "ok"
    mock_valkey.set.assert_awaited_once_with("banned_chat:-100555", "0", ex=3600)


async def test_cached_not_banned_skips_database(middleware):
    session = _session(banned=None)
    handler = AsyncMock(return_value="ok")

    with patch("app.bot.middlewares.banned.valkey") as mock_valkey:
        mock_valkey.get = AsyncMock(return_value="0")
        mock_valkey.set = AsyncMock()
        result = await middleware(handler, _message_event(), {"session": session})

    assert result == "ok"
    session.execute.assert_not_awaited()
    mock_valkey.set.assert_not_awaited()


async def test_cached_banned_still_blocks(middleware):
    handler = AsyncMock()

    with patch("app.bot.middlewares.banned.valkey") as mock_valkey:
        mock_valkey.get = AsyncMock(return_value="1")
        result = await middleware(handler, _message_event(), {"session": _session(None)})

    assert result is None
    handler.assert_not_awaited()


async def test_banned_in_database_is_cached_as_banned(middleware):
    handler = AsyncMock()

    with patch("app.bot.middlewares.banned.valkey") as mock_valkey:
        mock_valkey.get = AsyncMock(return_value=None)
        mock_valkey.set = AsyncMock()
        result = await middleware(handler, _message_event(), {"session": _session(MagicMock())})

    assert result is None
    handler.assert_not_awaited()
    mock_valkey.set.assert_awaited_once_with("banned_chat:-100555", "1", ex=3600)


async def test_callback_without_message_passes(middleware):
    """Callback от inline-сообщения не несёт message -- middleware не должен падать."""
    event = MagicMock(spec=Update)
    event.message = None
    event.callback_query = MagicMock(message=None)
    event.my_chat_member = None
    handler = AsyncMock(return_value="ok")

    assert await middleware(handler, event, {}) == "ok"


async def test_banned_middleware_runs_before_upserts():
    """Забаненный чат отсекается до апсертов чата/пользователя, но после выдачи сессии."""
    from app.bot.handlers.creation_private import dm_router

    dm_router._parent_router = None

    from app.bot.dispatcher import dp
    from app.bot.middlewares.banned import BannedChatMiddleware
    from app.bot.middlewares.chat import ChatMiddleware
    from app.bot.middlewares.database import DatabaseMiddleware
    from app.bot.middlewares.user import UserMiddleware
    from app.bot.middlewares.user_chat import UserChatMiddleware

    order = [type(m) for m in dp.update.middleware]
    banned = order.index(BannedChatMiddleware)

    assert order.index(DatabaseMiddleware) < banned
    assert banned < order.index(ChatMiddleware)
    assert banned < order.index(UserMiddleware)
    assert banned < order.index(UserChatMiddleware)
