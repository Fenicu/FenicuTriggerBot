"""Регрессия: /tag и /deltag не должны трогать посты, отправленные от имени чата."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user_chat import UserChat
from tests.factories import create_chat, create_user


def _make_i18n():
    i18n = MagicMock()
    i18n.error.no.rights.return_value = "No rights"
    i18n.tag.usage.return_value = "Usage: /tag <text>"
    i18n.tag.reply.required.return_value = "Reply required"
    i18n.tag.sender.chat.return_value = "Sender chat"
    i18n.tag.invalid.return_value = "Invalid tag"
    i18n.tag.set.return_value = "Tag set"
    i18n.tag.cleared.return_value = "Tag cleared"
    i18n.user.missing.return_value = "User not found"
    i18n.error.unknown.return_value = "Unknown error"
    return i18n


def _make_message(reply_user):
    msg = MagicMock()
    msg.chat = MagicMock(id=-100123, type="supergroup")
    msg.from_user = MagicMock(id=456)
    msg.answer = AsyncMock()
    member = MagicMock(status="administrator")
    msg.chat.get_member = AsyncMock(return_value=member)

    reply = MagicMock()
    reply.from_user = reply_user
    reply.sender_chat = MagicMock(id=-100999)
    msg.reply_to_message = reply
    return msg


def _make_command(args="Elite"):
    cmd = MagicMock()
    cmd.args = args
    return cmd


@pytest.fixture
async def chat(db_session: AsyncSession):
    return await create_chat(db_session, tags_enabled=True)


@pytest.fixture
async def user(db_session: AsyncSession):
    return await create_user(db_session)


async def test_tag_refuses_chat_sender(db_session, chat, user):
    from app.bot.handlers.reputation import tag_command

    uc = UserChat(user_id=user.id, chat_id=chat.id)
    db_session.add(uc)
    await db_session.flush()

    target = MagicMock(id=user.id)
    msg = _make_message(target)

    with patch("app.bot.handlers.reputation.set_manual_tag", new_callable=AsyncMock) as mock_set:
        await tag_command(msg, _make_command("Elite"), db_session, _make_i18n(), chat)

    mock_set.assert_not_awaited()
    msg.answer.assert_awaited_once_with("Sender chat", parse_mode="HTML")


async def test_deltag_refuses_chat_sender(db_session, chat, user):
    from app.bot.handlers.reputation import deltag_command

    uc = UserChat(user_id=user.id, chat_id=chat.id, tag="Custom", tag_is_manual=True)
    db_session.add(uc)
    await db_session.flush()

    target = MagicMock(id=user.id)
    msg = _make_message(target)

    with patch("app.bot.handlers.reputation.clear_manual_tag", new_callable=AsyncMock) as mock_clear:
        await deltag_command(msg, db_session, _make_i18n(), chat)

    mock_clear.assert_not_awaited()
    msg.answer.assert_awaited_once_with("Sender chat", parse_mode="HTML")
