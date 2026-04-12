"""Tests for app/bot/handlers/common.py — /start command handler."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_i18n():
    i18n = MagicMock()
    i18n.start.message.return_value = "Welcome to Trigger Bot"
    i18n.captcha.missing.return_value = "Captcha not found"
    i18n.captcha.wrong.user.return_value = "Wrong user"
    i18n.captcha.already.completed.return_value = "Already completed"
    i18n.captcha.expired.return_value = "Captcha expired"
    i18n.captcha.open.webapp.return_value = "Open webapp"
    i18n.captcha.invalid.link.return_value = "Invalid link"
    i18n.btn.verify.return_value = "Verify"
    i18n.settings.no.admin.return_value = "Not an admin"
    i18n.settings.chat.missing.return_value = "Chat missing"
    i18n.settings.open.webapp.return_value = "Open settings"
    i18n.settings.webapp.sent.return_value = "Settings sent"
    return i18n


def _make_message(user_id=456, text="/start", chat_type="private"):
    msg = MagicMock()
    msg.chat = MagicMock(id=user_id, type=chat_type)
    msg.from_user = MagicMock(id=user_id, username="testuser", full_name="Test User")
    msg.text = text
    msg.answer = AsyncMock()
    return msg


# ── /start basic ──────────────────────────────────────────────────────────────


async def test_start_basic(db_session):
    from app.bot.handlers.common import start_command

    msg = _make_message(text="/start")
    i18n = _make_i18n()

    await start_command(msg, i18n, db_session)

    msg.answer.assert_awaited_once()
    call_args = msg.answer.call_args
    assert call_args.args[0] == "Welcome to Trigger Bot"


# ── /start captcha deep link ─────────────────────────────────────────────────


async def test_start_captcha_missing_session(db_session):
    from app.bot.handlers.common import start_command

    msg = _make_message(text="/start captcha_99999")
    i18n = _make_i18n()

    await start_command(msg, i18n, db_session)

    msg.answer.assert_awaited_once_with("Captcha not found", parse_mode="HTML")


async def test_start_captcha_invalid_link(db_session):
    from app.bot.handlers.common import start_command

    msg = _make_message(text="/start captcha_notanumber")
    i18n = _make_i18n()

    await start_command(msg, i18n, db_session)

    msg.answer.assert_awaited_once_with("Invalid link", parse_mode="HTML")


# ── /start settings deep link ────────────────────────────────────────────────


@patch("app.bot.handlers.common.bot")
async def test_start_settings_admin_ok(mock_bot, db_session):
    from app.bot.handlers.common import start_command

    member = MagicMock()
    member.status = "administrator"
    mock_bot.get_chat_member = AsyncMock(return_value=member)

    msg = _make_message(text="/start settings_-100123456")
    i18n = _make_i18n()

    await start_command(msg, i18n, db_session)

    msg.answer.assert_awaited_once()
    call_args = msg.answer.call_args
    assert call_args.args[0] == "Settings sent"
    assert call_args.kwargs.get("reply_markup") is not None


@patch("app.bot.handlers.common.bot")
async def test_start_settings_not_admin(mock_bot, db_session):
    from app.bot.handlers.common import start_command

    member = MagicMock()
    member.status = "member"
    mock_bot.get_chat_member = AsyncMock(return_value=member)

    msg = _make_message(text="/start settings_-100123456")
    i18n = _make_i18n()

    await start_command(msg, i18n, db_session)

    msg.answer.assert_awaited_once_with("Not an admin", parse_mode="HTML")


@patch("app.bot.handlers.common.bot")
async def test_start_settings_chat_error(mock_bot, db_session):
    from app.bot.handlers.common import start_command

    mock_bot.get_chat_member = AsyncMock(side_effect=Exception("Chat not found"))

    msg = _make_message(text="/start settings_-100123456")
    i18n = _make_i18n()

    await start_command(msg, i18n, db_session)

    msg.answer.assert_awaited_once_with("Chat missing", parse_mode="HTML")


async def test_start_settings_invalid_chat_id(db_session):
    from app.bot.handlers.common import start_command

    msg = _make_message(text="/start settings_notanumber")
    i18n = _make_i18n()

    await start_command(msg, i18n, db_session)

    # Falls through to default start message
    msg.answer.assert_awaited_once()
    assert msg.answer.call_args.args[0] == "Welcome to Trigger Bot"


# ── /start with unknown deep link ────────────────────────────────────────────


async def test_start_unknown_deep_link(db_session):
    from app.bot.handlers.common import start_command

    msg = _make_message(text="/start something_random")
    i18n = _make_i18n()

    await start_command(msg, i18n, db_session)

    msg.answer.assert_awaited_once()
    assert msg.answer.call_args.args[0] == "Welcome to Trigger Bot"
