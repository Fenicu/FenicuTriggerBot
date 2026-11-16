"""Регрессия /status: уровень считается по очкам и порогам, а не берётся из колонки."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user_chat import UserChat
from tests.factories import create_chat, create_user


def _make_i18n():
    i18n = MagicMock()
    i18n.reputation.group.only.return_value = "Groups only"
    i18n.reputation.disabled.return_value = "Reputation disabled"
    i18n.reputation.no.data.return_value = "No data"
    i18n.reputation.status.side_effect = lambda **kwargs: f"level={kwargs['level']} name={kwargs['level_name']}"
    i18n.reputation.next.level.side_effect = lambda **kwargs: f"next in {kwargs['remaining']}"
    i18n.reputation.max.level.return_value = "Max level!"
    return i18n


def _make_message(user_id: int, chat_id: int):
    msg = MagicMock()
    msg.chat = MagicMock(id=chat_id, type="supergroup")
    msg.from_user = MagicMock(id=user_id)
    msg.answer = AsyncMock()
    msg.ephemeral_message_id = None
    return msg


async def _status_text(db_session: AsyncSession, chat, user_chat: UserChat, monkeypatch) -> str:
    from app.bot.handlers.reputation import status_command

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr("app.bot.handlers.reputation.bot", mock_bot)

    db_session.add(user_chat)
    await db_session.flush()

    msg = _make_message(user_chat.user_id, chat.id)
    await status_command(msg, db_session, _make_i18n(), chat)

    _, kwargs = mock_bot.send_message.call_args
    return kwargs["text"]


@pytest.fixture
async def chat(db_session: AsyncSession):
    return await create_chat(db_session, tags_enabled=True, tags_preset="neutral", language_code="ru")


@pytest.fixture
async def user(db_session: AsyncSession):
    return await create_user(db_session)


async def test_status_ignores_stale_level_column(db_session, chat, user, monkeypatch):
    """В колонке уровень 3, по очкам — 1: показываем уровень 1."""
    uc = UserChat(user_id=user.id, chat_id=chat.id, reputation_score=100, reputation_level=3)

    text = await _status_text(db_session, chat, uc, monkeypatch)

    assert "level=1" in text
    assert "name=Участник" in text


async def test_status_uses_high_computed_level(db_session, chat, user, monkeypatch):
    uc = UserChat(user_id=user.id, chat_id=chat.id, reputation_score=250, reputation_level=0)

    text = await _status_text(db_session, chat, uc, monkeypatch)

    assert "level=2" in text
    assert "name=Активный" in text


async def test_status_level_matches_tag_when_tag_out_of_sync(db_session, chat, user, monkeypatch):
    """Тег мог остаться от прошлого уровня — уровень берём из очков."""
    uc = UserChat(user_id=user.id, chat_id=chat.id, reputation_score=100, reputation_level=5, tag="Легенда")

    text = await _status_text(db_session, chat, uc, monkeypatch)

    assert "level=1" in text
