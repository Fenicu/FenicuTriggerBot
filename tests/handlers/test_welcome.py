"""Tests for app/bot/handlers/welcome.py — /welcome command."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import create_chat


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_i18n():
    i18n = MagicMock()
    i18n.error.no.rights.return_value = "No rights"
    i18n.welcome.usage.return_value = "Usage: /welcome set|delete|test"
    i18n.welcome.set.no.reply.return_value = "Reply to a message"
    i18n.welcome.set.success.return_value = "Welcome set"
    i18n.welcome.disabled.return_value = "Welcome disabled"
    i18n.welcome.unset.return_value = "No welcome set"
    i18n.welcome.invalid.timeout.return_value = "Invalid timeout"
    i18n.error.unknown.return_value = "Unknown error"
    return i18n


def _make_command(args=None):
    cmd = MagicMock()
    cmd.args = args
    return cmd


def _make_message(chat_id=-100123, user_id=456, member_status="administrator",
                  reply_msg=None):
    msg = MagicMock()
    msg.chat = MagicMock(id=chat_id, type="supergroup")
    msg.from_user = MagicMock(id=user_id, username="admin", full_name="Admin")
    msg.answer = AsyncMock()

    member = MagicMock()
    member.status = member_status
    msg.chat.get_member = AsyncMock(return_value=member)

    if reply_msg is not None:
        msg.reply_to_message = reply_msg
    else:
        msg.reply_to_message = None

    return msg


def _make_reply_message():
    reply = MagicMock()
    reply.html_text = "<b>Welcome!</b>"
    reply.model_dump.return_value = {"text": "Welcome!"}
    return reply


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def chat(db_session: AsyncSession):
    return await create_chat(db_session)


@pytest.fixture
async def chat_with_welcome(db_session: AsyncSession):
    return await create_chat(
        db_session,
        welcome_enabled=True,
        welcome_message={"text": "Hello newcomer!"},
    )


# ── Permission check ─────────────────────────────────────────────────────────


async def test_welcome_not_admin(db_session, chat):
    from app.bot.handlers.welcome import welcome_command

    msg = _make_message(chat_id=chat.id, member_status="member")
    i18n = _make_i18n()

    await welcome_command(msg, _make_command("set"), db_session, i18n, chat)

    msg.answer.assert_awaited_once_with("No rights", parse_mode="HTML")


# ── No action ─────────────────────────────────────────────────────────────────


async def test_welcome_no_action(db_session, chat):
    from app.bot.handlers.welcome import welcome_command

    msg = _make_message(chat_id=chat.id)
    i18n = _make_i18n()

    await welcome_command(msg, _make_command(None), db_session, i18n, chat)

    msg.answer.assert_awaited_once_with("Usage: /welcome set|delete|test", parse_mode="HTML")


# ── /welcome set ──────────────────────────────────────────────────────────────


async def test_welcome_set_no_reply(db_session, chat):
    from app.bot.handlers.welcome import welcome_command

    msg = _make_message(chat_id=chat.id)
    i18n = _make_i18n()

    await welcome_command(msg, _make_command("set"), db_session, i18n, chat)

    msg.answer.assert_awaited_once_with("Reply to a message", parse_mode="HTML")


@patch("app.bot.handlers.welcome.update_chat_settings", new_callable=AsyncMock)
async def test_welcome_set_success(mock_update, db_session, chat):
    from app.bot.handlers.welcome import welcome_command

    reply = _make_reply_message()
    msg = _make_message(chat_id=chat.id, reply_msg=reply)
    i18n = _make_i18n()

    mock_update.return_value = chat

    await welcome_command(msg, _make_command("set"), db_session, i18n, chat)

    mock_update.assert_awaited_once()
    call_kwargs = mock_update.call_args.kwargs
    assert call_kwargs["welcome_enabled"] is True
    assert call_kwargs["welcome_message"] is not None
    msg.answer.assert_awaited_once_with("Welcome set", parse_mode="HTML")


@patch("app.bot.handlers.welcome.update_chat_settings", new_callable=AsyncMock)
async def test_welcome_set_with_timeout(mock_update, db_session, chat):
    from app.bot.handlers.welcome import welcome_command

    reply = _make_reply_message()
    msg = _make_message(chat_id=chat.id, reply_msg=reply)
    i18n = _make_i18n()

    mock_update.return_value = chat

    await welcome_command(msg, _make_command("set 5m"), db_session, i18n, chat)

    mock_update.assert_awaited_once()
    call_kwargs = mock_update.call_args.kwargs
    autodelete = call_kwargs["autodelete_settings"]
    assert autodelete["welcome"]["enabled"] is True
    assert autodelete["welcome"]["delay"] == 300  # 5m = 300s


@patch("app.bot.handlers.welcome.update_chat_settings", new_callable=AsyncMock)
async def test_welcome_set_with_numeric_timeout(mock_update, db_session, chat):
    from app.bot.handlers.welcome import welcome_command

    reply = _make_reply_message()
    msg = _make_message(chat_id=chat.id, reply_msg=reply)
    i18n = _make_i18n()

    mock_update.return_value = chat

    await welcome_command(msg, _make_command("set 120"), db_session, i18n, chat)

    mock_update.assert_awaited_once()
    call_kwargs = mock_update.call_args.kwargs
    autodelete = call_kwargs["autodelete_settings"]
    assert autodelete["welcome"]["delay"] == 120


async def test_welcome_set_invalid_timeout(db_session, chat):
    from app.bot.handlers.welcome import welcome_command

    reply = _make_reply_message()
    msg = _make_message(chat_id=chat.id, reply_msg=reply)
    i18n = _make_i18n()

    await welcome_command(msg, _make_command("set abc"), db_session, i18n, chat)

    msg.answer.assert_awaited_once_with("Invalid timeout", parse_mode="HTML")


@patch("app.bot.handlers.welcome.update_chat_settings", new_callable=AsyncMock)
async def test_welcome_set_timeout_capped_at_3600(mock_update, db_session, chat):
    from app.bot.handlers.welcome import welcome_command

    reply = _make_reply_message()
    msg = _make_message(chat_id=chat.id, reply_msg=reply)
    i18n = _make_i18n()

    mock_update.return_value = chat

    await welcome_command(msg, _make_command("set 9999"), db_session, i18n, chat)

    call_kwargs = mock_update.call_args.kwargs
    autodelete = call_kwargs["autodelete_settings"]
    assert autodelete["welcome"]["delay"] == 3600


# ── /welcome delete / off ────────────────────────────────────────────────────


@patch("app.bot.handlers.welcome.update_chat_settings", new_callable=AsyncMock)
async def test_welcome_delete(mock_update, db_session, chat_with_welcome):
    from app.bot.handlers.welcome import welcome_command

    msg = _make_message(chat_id=chat_with_welcome.id)
    i18n = _make_i18n()

    mock_update.return_value = chat_with_welcome

    await welcome_command(msg, _make_command("delete"), db_session, i18n, chat_with_welcome)

    mock_update.assert_awaited_once()
    call_kwargs = mock_update.call_args.kwargs
    assert call_kwargs["welcome_enabled"] is False
    assert call_kwargs["welcome_message"] is None
    msg.answer.assert_awaited_once_with("Welcome disabled", parse_mode="HTML")


@patch("app.bot.handlers.welcome.update_chat_settings", new_callable=AsyncMock)
async def test_welcome_off(mock_update, db_session, chat_with_welcome):
    from app.bot.handlers.welcome import welcome_command

    msg = _make_message(chat_id=chat_with_welcome.id)
    i18n = _make_i18n()

    mock_update.return_value = chat_with_welcome

    await welcome_command(msg, _make_command("off"), db_session, i18n, chat_with_welcome)

    mock_update.assert_awaited_once()
    call_kwargs = mock_update.call_args.kwargs
    assert call_kwargs["welcome_enabled"] is False


# ── /welcome test ─────────────────────────────────────────────────────────────


async def test_welcome_test_no_welcome_set(db_session, chat):
    from app.bot.handlers.welcome import welcome_command

    msg = _make_message(chat_id=chat.id)
    i18n = _make_i18n()

    await welcome_command(msg, _make_command("test"), db_session, i18n, chat)

    msg.answer.assert_awaited_once_with("No welcome set", parse_mode="HTML")


@patch("app.bot.handlers.welcome.send_welcome_message", new_callable=AsyncMock)
@patch("app.bot.handlers.welcome.bot")
async def test_welcome_test_success(mock_bot, mock_send, db_session, chat_with_welcome):
    from app.bot.handlers.welcome import welcome_command

    msg = _make_message(chat_id=chat_with_welcome.id)
    i18n = _make_i18n()

    mock_send.return_value = MagicMock()  # sent message

    await welcome_command(msg, _make_command("test"), db_session, i18n, chat_with_welcome)

    mock_send.assert_awaited_once()
    # Should not send error message
    msg.answer.assert_not_awaited()


@patch("app.bot.handlers.welcome.send_welcome_message", new_callable=AsyncMock)
@patch("app.bot.handlers.welcome.bot")
async def test_welcome_test_failure(mock_bot, mock_send, db_session, chat_with_welcome):
    from app.bot.handlers.welcome import welcome_command

    msg = _make_message(chat_id=chat_with_welcome.id)
    i18n = _make_i18n()

    mock_send.return_value = None  # send failed

    await welcome_command(msg, _make_command("test"), db_session, i18n, chat_with_welcome)

    msg.answer.assert_awaited_once_with("Unknown error", parse_mode="HTML")
