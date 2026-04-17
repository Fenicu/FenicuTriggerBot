"""Tests for app/bot/handlers/trust.py — /trust, /untrust, /add_mod, /del_mod commands."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from tests.factories import create_user


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_i18n():
    i18n = MagicMock()
    i18n.args.error.return_value = "Provide args"
    i18n.user.missing.return_value = "User not found"
    i18n.user.trusted.return_value = "User trusted"
    i18n.user.untrusted.return_value = "User untrusted"
    i18n.user.promoted.mod.return_value = "Promoted to mod"
    i18n.user.demoted.mod.return_value = "Demoted from mod"
    return i18n


def _make_command(args=None):
    cmd = MagicMock()
    cmd.args = args
    return cmd


def _make_message(user_id=456, text="/trust"):
    msg = MagicMock()
    msg.chat = MagicMock(id=user_id, type="private")
    msg.from_user = MagicMock(id=user_id, username="admin", full_name="Admin")
    msg.text = text
    msg.answer = AsyncMock()
    return msg


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def admin_user(db_session: AsyncSession):
    """A user whose ID is in BOT_ADMINS."""
    return await create_user(db_session, id=456, username="admin", first_name="Admin")


@pytest.fixture
async def mod_user(db_session: AsyncSession):
    """A bot moderator (not in BOT_ADMINS)."""
    return await create_user(db_session, id=789, username="moderator", first_name="Mod", is_bot_moderator=True)


@pytest.fixture
async def target_user(db_session: AsyncSession):
    """A regular user to be trusted/untrusted."""
    return await create_user(db_session, id=555, username="target", first_name="Target")


# ── /trust ────────────────────────────────────────────────────────────────────


@patch("app.bot.handlers.trust.settings")
async def test_trust_by_admin(mock_settings, db_session, admin_user, target_user):
    from app.bot.handlers.trust import trust_user

    mock_settings.BOT_ADMINS = [456]

    msg = _make_message(user_id=456)
    i18n = _make_i18n()

    await trust_user(msg, _make_command("555"), db_session, i18n, admin_user)

    await db_session.refresh(target_user)
    assert target_user.is_trusted is True
    msg.answer.assert_awaited_once_with("User trusted", parse_mode="HTML")


@patch("app.bot.handlers.trust.settings")
async def test_trust_by_moderator(mock_settings, db_session, mod_user, target_user):
    from app.bot.handlers.trust import trust_user

    mock_settings.BOT_ADMINS = []

    msg = _make_message(user_id=789)
    i18n = _make_i18n()

    await trust_user(msg, _make_command("555"), db_session, i18n, mod_user)

    await db_session.refresh(target_user)
    assert target_user.is_trusted is True


@patch("app.bot.handlers.trust.settings")
async def test_trust_by_regular_user_denied(mock_settings, db_session, target_user):
    from app.bot.handlers.trust import trust_user

    mock_settings.BOT_ADMINS = []
    regular = await create_user(db_session, id=333, username="nobody")

    msg = _make_message(user_id=333)
    i18n = _make_i18n()

    await trust_user(msg, _make_command("555"), db_session, i18n, regular)

    msg.answer.assert_not_awaited()
    await db_session.refresh(target_user)
    assert target_user.is_trusted is False


@patch("app.bot.handlers.trust.settings")
async def test_trust_no_args(mock_settings, db_session, admin_user):
    from app.bot.handlers.trust import trust_user

    mock_settings.BOT_ADMINS = [456]

    msg = _make_message(user_id=456)
    i18n = _make_i18n()

    await trust_user(msg, _make_command(None), db_session, i18n, admin_user)

    msg.answer.assert_awaited_once_with("Provide args", parse_mode="HTML")


@patch("app.bot.handlers.trust.settings")
async def test_trust_user_not_found(mock_settings, db_session, admin_user):
    from app.bot.handlers.trust import trust_user

    mock_settings.BOT_ADMINS = [456]

    msg = _make_message(user_id=456)
    i18n = _make_i18n()

    await trust_user(msg, _make_command("999999"), db_session, i18n, admin_user)

    msg.answer.assert_awaited_once_with("User not found", parse_mode="HTML")


@patch("app.bot.handlers.trust.settings")
async def test_trust_by_username(mock_settings, db_session, admin_user, target_user):
    from app.bot.handlers.trust import trust_user

    mock_settings.BOT_ADMINS = [456]

    msg = _make_message(user_id=456)
    i18n = _make_i18n()

    await trust_user(msg, _make_command("target"), db_session, i18n, admin_user)

    await db_session.refresh(target_user)
    assert target_user.is_trusted is True


# ── /untrust ──────────────────────────────────────────────────────────────────


@patch("app.bot.handlers.trust.settings")
async def test_untrust_success(mock_settings, db_session, admin_user, target_user):
    from app.bot.handlers.trust import untrust_user

    mock_settings.BOT_ADMINS = [456]

    target_user.is_trusted = True
    await db_session.commit()

    msg = _make_message(user_id=456)
    i18n = _make_i18n()

    await untrust_user(msg, _make_command("555"), db_session, i18n, admin_user)

    await db_session.refresh(target_user)
    assert target_user.is_trusted is False
    msg.answer.assert_awaited_once_with("User untrusted", parse_mode="HTML")


@patch("app.bot.handlers.trust.settings")
async def test_untrust_no_args(mock_settings, db_session, admin_user):
    from app.bot.handlers.trust import untrust_user

    mock_settings.BOT_ADMINS = [456]

    msg = _make_message(user_id=456)
    i18n = _make_i18n()

    await untrust_user(msg, _make_command(None), db_session, i18n, admin_user)

    msg.answer.assert_awaited_once_with("Provide args", parse_mode="HTML")


@patch("app.bot.handlers.trust.settings")
async def test_untrust_user_not_found(mock_settings, db_session, admin_user):
    from app.bot.handlers.trust import untrust_user

    mock_settings.BOT_ADMINS = [456]

    msg = _make_message(user_id=456)
    i18n = _make_i18n()

    await untrust_user(msg, _make_command("999999"), db_session, i18n, admin_user)

    msg.answer.assert_awaited_once_with("User not found", parse_mode="HTML")


# ── /add_mod ──────────────────────────────────────────────────────────────────


@patch("app.bot.handlers.trust.settings")
async def test_add_mod_success(mock_settings, db_session, admin_user, target_user):
    from app.bot.handlers.trust import add_mod

    mock_settings.BOT_ADMINS = [456]

    msg = _make_message(user_id=456)
    i18n = _make_i18n()

    await add_mod(msg, _make_command("555"), db_session, i18n, admin_user)

    await db_session.refresh(target_user)
    assert target_user.is_bot_moderator is True
    assert target_user.is_trusted is True


@patch("app.bot.handlers.trust.settings")
async def test_add_mod_not_bot_admin(mock_settings, db_session, mod_user, target_user):
    from app.bot.handlers.trust import add_mod

    mock_settings.BOT_ADMINS = []

    msg = _make_message(user_id=789)
    i18n = _make_i18n()

    await add_mod(msg, _make_command("555"), db_session, i18n, mod_user)

    # Only BOT_ADMINS can add mods, not moderators
    msg.answer.assert_not_awaited()


# ── /del_mod ──────────────────────────────────────────────────────────────────


@patch("app.bot.handlers.trust.settings")
async def test_del_mod_success(mock_settings, db_session, admin_user, target_user):
    from app.bot.handlers.trust import del_mod

    mock_settings.BOT_ADMINS = [456]
    target_user.is_bot_moderator = True
    await db_session.commit()

    msg = _make_message(user_id=456)
    i18n = _make_i18n()

    await del_mod(msg, _make_command("555"), db_session, i18n, admin_user)

    await db_session.refresh(target_user)
    assert target_user.is_bot_moderator is False
