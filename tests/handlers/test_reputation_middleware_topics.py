"""Регрессия: служебное сообщение темы форума не считается ответом."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message


@pytest.fixture
def middleware():
    from app.bot.middlewares.reputation import ReputationMiddleware

    return ReputationMiddleware()


def _make_event(reply_to):
    user = MagicMock()
    user.id = 42
    user.is_bot = False

    msg = MagicMock(spec=Message)
    msg.from_user = user
    msg.message_id = 123
    msg.reply_to_message = reply_to
    return msg


def _make_topic_service_message(creator_id: int = 55):
    creator = MagicMock()
    creator.id = creator_id
    creator.is_bot = False

    reply = MagicMock(spec=Message)
    reply.from_user = creator
    reply.forum_topic_created = MagicMock()
    reply.message_id = 100
    return reply


def _make_regular_reply(author_id: int = 55):
    author = MagicMock()
    author.id = author_id
    author.is_bot = False

    reply = MagicMock(spec=Message)
    reply.from_user = author
    reply.forum_topic_created = None
    reply.message_id = 100
    return reply


def _make_chat():
    db_chat = MagicMock()
    db_chat.tags_enabled = True
    db_chat.type = "supergroup"
    db_chat.id = -100
    return db_chat


async def _run(middleware, event):
    session = AsyncMock()
    session.get = AsyncMock(return_value=MagicMock())
    handler = AsyncMock(return_value="ok")

    with (
        patch("app.bot.middlewares.reputation.add_message_score", new_callable=AsyncMock, return_value=None),
        patch("app.bot.middlewares.reputation.add_reply_score", new_callable=AsyncMock, return_value=None) as mock_reply,
        patch("app.bot.middlewares.reputation.valkey") as mock_valkey,
    ):
        mock_valkey.set = AsyncMock()
        await middleware(handler, event, {"db_chat": _make_chat(), "session": session})

    return mock_reply


async def test_topic_service_message_is_not_counted_as_reply(middleware):
    mock_reply = await _run(middleware, _make_event(_make_topic_service_message()))

    mock_reply.assert_not_awaited()


async def test_regular_reply_still_awards_points(middleware):
    mock_reply = await _run(middleware, _make_event(_make_regular_reply()))

    mock_reply.assert_awaited_once()
