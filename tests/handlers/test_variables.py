"""Tests for app/bot/handlers/variables.py — /setvar, /delvar, /vars commands."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import create_chat


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_i18n():
    i18n = MagicMock()
    i18n.error.no.rights.return_value = "No rights"
    i18n.var.usage.set.return_value = "Usage: /setvar key value"
    i18n.var.usage.delete.return_value = "Usage: /delvar key"
    i18n.var.invalid.key.return_value = "Invalid key"
    i18n.var.set.return_value = "Variable set"
    i18n.var.deleted.return_value = "Variable deleted"
    i18n.var.missing.return_value = "Variable not found"
    i18n.var.list.empty.return_value = "No variables"
    i18n.var.list.header.return_value = "Variables:"
    i18n.ephemeral.fallback.notice.return_value = "Ответ отправлен в личные сообщения"
    return i18n


def _make_command(args=None):
    cmd = MagicMock()
    cmd.args = args
    return cmd


def _make_message(chat_id=-100123, user_id=456, member_status="administrator"):
    msg = MagicMock()
    msg.chat = MagicMock(id=chat_id, type="supergroup")
    msg.from_user = MagicMock(id=user_id, username="admin", full_name="Admin")
    msg.answer = AsyncMock()
    msg.ephemeral_message_id = None

    member = MagicMock()
    member.status = member_status
    msg.chat.get_member = AsyncMock(return_value=member)

    return msg


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def chat(db_session: AsyncSession):
    return await create_chat(db_session)


# ── /setvar ───────────────────────────────────────────────────────────────────


async def test_setvar_not_admin(db_session, chat):
    from app.bot.handlers.variables import set_var_command

    msg = _make_message(chat_id=chat.id, member_status="member")
    i18n = _make_i18n()

    await set_var_command(msg, _make_command("key value"), db_session, i18n)

    msg.answer.assert_awaited_once_with("No rights", parse_mode="HTML")


async def test_setvar_no_args(db_session, chat):
    from app.bot.handlers.variables import set_var_command

    msg = _make_message(chat_id=chat.id)
    i18n = _make_i18n()

    await set_var_command(msg, _make_command(None), db_session, i18n)

    msg.answer.assert_awaited_once_with("Usage: /setvar key value", parse_mode="HTML")


async def test_setvar_key_only_no_value(db_session, chat):
    from app.bot.handlers.variables import set_var_command

    msg = _make_message(chat_id=chat.id)
    i18n = _make_i18n()

    await set_var_command(msg, _make_command("onlykey"), db_session, i18n)

    msg.answer.assert_awaited_once_with("Usage: /setvar key value", parse_mode="HTML")


async def test_setvar_invalid_key(db_session, chat):
    from app.bot.handlers.variables import set_var_command

    msg = _make_message(chat_id=chat.id)
    i18n = _make_i18n()

    await set_var_command(msg, _make_command("bad-key! value"), db_session, i18n)

    msg.answer.assert_awaited_once_with("Invalid key", parse_mode="HTML")


async def test_setvar_success(db_session, chat):
    from app.bot.handlers.variables import set_var_command

    msg = _make_message(chat_id=chat.id)
    i18n = _make_i18n()

    await set_var_command(msg, _make_command("greeting Hello World"), db_session, i18n)

    msg.answer.assert_awaited_once_with("Variable set", parse_mode="HTML")

    # Verify it was actually saved
    from app.services.chat_variable_service import get_vars

    variables = await get_vars(db_session, chat.id)
    assert variables["greeting"] == "Hello World"


async def test_setvar_overwrite(db_session, chat):
    from app.bot.handlers.variables import set_var_command
    from app.services.chat_variable_service import set_var

    await set_var(db_session, chat.id, "name", "old_value")

    msg = _make_message(chat_id=chat.id)
    i18n = _make_i18n()

    await set_var_command(msg, _make_command("name new_value"), db_session, i18n)

    from app.services.chat_variable_service import get_vars

    variables = await get_vars(db_session, chat.id)
    assert variables["name"] == "new_value"


# ── /delvar ───────────────────────────────────────────────────────────────────


async def test_delvar_not_admin(db_session, chat):
    from app.bot.handlers.variables import del_var_command

    msg = _make_message(chat_id=chat.id, member_status="member")
    i18n = _make_i18n()

    await del_var_command(msg, _make_command("key"), db_session, i18n)

    msg.answer.assert_awaited_once_with("No rights", parse_mode="HTML")


async def test_delvar_no_args(db_session, chat):
    from app.bot.handlers.variables import del_var_command

    msg = _make_message(chat_id=chat.id)
    i18n = _make_i18n()

    await del_var_command(msg, _make_command(None), db_session, i18n)

    msg.answer.assert_awaited_once_with("Usage: /delvar key", parse_mode="HTML")


async def test_delvar_success(db_session, chat):
    from app.bot.handlers.variables import del_var_command
    from app.services.chat_variable_service import set_var

    await set_var(db_session, chat.id, "name", "value")

    msg = _make_message(chat_id=chat.id)
    i18n = _make_i18n()

    await del_var_command(msg, _make_command("name"), db_session, i18n)

    msg.answer.assert_awaited_once_with("Variable deleted", parse_mode="HTML")


async def test_delvar_missing(db_session, chat):
    from app.bot.handlers.variables import del_var_command

    msg = _make_message(chat_id=chat.id)
    i18n = _make_i18n()

    await del_var_command(msg, _make_command("nonexistent"), db_session, i18n)

    msg.answer.assert_awaited_once_with("Variable not found", parse_mode="HTML")


# ── /vars ─────────────────────────────────────────────────────────────────────


async def test_vars_not_admin(db_session, chat, monkeypatch):
    from app.bot.handlers.variables import list_vars_command

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr("app.bot.handlers.variables.bot", mock_bot)

    msg = _make_message(chat_id=chat.id, member_status="member")
    i18n = _make_i18n()

    await list_vars_command(msg, db_session, i18n)

    mock_bot.send_message.assert_awaited_once()
    _, kwargs = mock_bot.send_message.call_args
    assert kwargs["text"] == "No rights"
    assert kwargs["receiver_user_id"] == msg.from_user.id


async def test_vars_empty(db_session, chat, monkeypatch):
    from app.bot.handlers.variables import list_vars_command

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr("app.bot.handlers.variables.bot", mock_bot)

    msg = _make_message(chat_id=chat.id)
    i18n = _make_i18n()

    await list_vars_command(msg, db_session, i18n)

    mock_bot.send_message.assert_awaited_once()
    _, kwargs = mock_bot.send_message.call_args
    assert kwargs["text"] == "No variables"
    assert kwargs["receiver_user_id"] == msg.from_user.id


async def test_vars_with_data(db_session, chat, monkeypatch):
    from app.bot.handlers.variables import list_vars_command
    from app.services.chat_variable_service import set_var

    await set_var(db_session, chat.id, "greeting", "Hello")
    await set_var(db_session, chat.id, "farewell", "Bye")

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr("app.bot.handlers.variables.bot", mock_bot)

    msg = _make_message(chat_id=chat.id)
    i18n = _make_i18n()

    await list_vars_command(msg, db_session, i18n)

    mock_bot.send_message.assert_awaited_once()
    _, kwargs = mock_bot.send_message.call_args
    text = kwargs["text"]
    assert "Variables:" in text
    assert "greeting" in text
    assert "farewell" in text
