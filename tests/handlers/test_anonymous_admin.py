"""Анонимный админ: from_user — общий GroupAnonymousBot, права определяются по sender_chat."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat_variable import ChatVariable
from app.db.models.trigger import AccessLevel, Trigger
from tests.factories import create_chat, create_user

ANONYMOUS_BOT_ID = 1087968824


def _anonymous_message(chat_id: int, reply_content: dict | None = None) -> MagicMock:
    msg = MagicMock()
    msg.chat = MagicMock(id=chat_id, type="supergroup")
    msg.sender_chat = MagicMock(id=chat_id)
    msg.from_user = MagicMock(id=ANONYMOUS_BOT_ID, username="GroupAnonymousBot", full_name="Group")
    msg.answer = AsyncMock()
    msg.ephemeral_message_id = None
    # Telegram не считает GroupAnonymousBot участником чата
    msg.chat.get_member = AsyncMock(
        side_effect=TelegramBadRequest(method=MagicMock(), message="Bad Request: PARTICIPANT_ID_INVALID")
    )
    if reply_content is not None:
        reply = MagicMock()
        reply.content_type = "text"
        reply.model_dump_json.return_value = json.dumps(reply_content)
        msg.reply_to_message = reply
    return msg


def _trigger(access_level: AccessLevel) -> MagicMock:
    trigger = MagicMock()
    trigger.access_level = access_level
    return trigger


@pytest.fixture
async def chat(db_session: AsyncSession):
    return await create_chat(db_session, admins_only_add=True)


@pytest.fixture
async def anon_user(db_session: AsyncSession):
    return await create_user(db_session, id=ANONYMOUS_BOT_ID, first_name="Group", is_bot=True)


async def test_check_access_admins_trigger_allows_anonymous_admin():
    from app.bot.handlers.matching import _check_access

    msg = _anonymous_message(-100500)

    assert await _check_access(_trigger(AccessLevel.ADMINS), msg) is True
    msg.chat.get_member.assert_not_awaited()


async def test_check_access_owner_trigger_denies_anonymous_admin():
    from app.bot.handlers.matching import _check_access

    msg = _anonymous_message(-100500)

    assert await _check_access(_trigger(AccessLevel.OWNER), msg) is False
    msg.chat.get_member.assert_not_awaited()


async def test_check_access_foreign_sender_chat_is_not_admin():
    """Сообщение от имени другого канала не даёт прав админа."""
    from app.bot.handlers.matching import _check_access

    msg = _anonymous_message(-100500)
    msg.sender_chat = MagicMock(id=-100777)
    msg.chat.get_member = AsyncMock(return_value=MagicMock(status="left"))

    assert await _check_access(_trigger(AccessLevel.ADMINS), msg) is False


async def test_add_in_admins_only_chat_allows_anonymous_admin(db_session: AsyncSession, chat, anon_user):
    from app.bot.handlers.creation import add_trigger

    msg = _anonymous_message(chat.id, reply_content={"text": "hi"})
    command = MagicMock(args="anonkey")

    await add_trigger(msg, command, db_session, MagicMock(), chat, anon_user)

    trigger = (await db_session.execute(select(Trigger).where(Trigger.chat_id == chat.id))).scalars().first()
    assert trigger is not None
    assert trigger.created_by == ANONYMOUS_BOT_ID
    msg.chat.get_member.assert_not_awaited()


async def test_add_in_admins_only_chat_get_member_error_means_no_rights(db_session: AsyncSession, chat, anon_user):
    """Ошибка getChatMember не роняет /add, а трактуется как отсутствие прав."""
    from app.bot.handlers.creation import add_trigger

    msg = _anonymous_message(chat.id, reply_content={"text": "hi"})
    msg.sender_chat = None
    i18n = MagicMock()
    i18n.error.no.rights.return_value = "No rights"

    await add_trigger(msg, MagicMock(args="anonkey"), db_session, i18n, chat, anon_user)

    assert msg.answer.call_args.args[0] == "No rights"
    assert (await db_session.execute(select(Trigger).where(Trigger.chat_id == chat.id))).scalars().first() is None


async def test_setvar_allows_anonymous_admin(db_session: AsyncSession, chat):
    from app.bot.handlers.variables import set_var_command

    msg = _anonymous_message(chat.id)

    await set_var_command(msg, MagicMock(args="greeting hello"), db_session, MagicMock())

    var = (await db_session.execute(select(ChatVariable).where(ChatVariable.chat_id == chat.id))).scalars().first()
    assert var is not None
    assert var.value == "hello"


async def test_delvar_allows_anonymous_admin(db_session: AsyncSession, chat):
    from app.bot.handlers.variables import del_var_command, set_var_command

    msg = _anonymous_message(chat.id)
    await set_var_command(msg, MagicMock(args="greeting hello"), db_session, MagicMock())

    i18n = MagicMock()
    await del_var_command(msg, MagicMock(args="greeting"), db_session, i18n)

    i18n.var.deleted.assert_called_once()


async def test_vars_allows_anonymous_admin(db_session: AsyncSession, chat, monkeypatch):
    from app.bot.handlers.variables import list_vars_command

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr("app.bot.handlers.variables.bot", mock_bot)
    i18n = MagicMock()
    i18n.var.list.empty.return_value = "No variables"
    i18n.error.no.rights.return_value = "No rights"

    await list_vars_command(_anonymous_message(chat.id), db_session, i18n)

    assert mock_bot.send_message.call_args.kwargs["text"] == "No variables"
