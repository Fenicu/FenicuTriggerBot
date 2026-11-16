"""Регрессия /trust, /untrust, /add_mod: username ищется без учёта регистра."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import create_user


def _make_i18n():
    i18n = MagicMock()
    i18n.args.error.return_value = "Provide args"
    i18n.user.missing.return_value = "User not found"
    i18n.user.ambiguous.return_value = "Ambiguous username"
    i18n.user.trusted.side_effect = lambda **kwargs: f"trusted {kwargs['user']}"
    i18n.user.untrusted.side_effect = lambda **kwargs: f"untrusted {kwargs['user']}"
    i18n.user.promoted.mod.side_effect = lambda **kwargs: f"mod {kwargs['user']}"
    return i18n


def _make_command(args=None):
    cmd = MagicMock()
    cmd.args = args
    return cmd


def _make_message():
    msg = MagicMock()
    msg.chat = MagicMock(id=456, type="private")
    msg.from_user = MagicMock(id=456, username="admin")
    msg.answer = AsyncMock()
    return msg


@pytest.fixture
async def admin_user(db_session: AsyncSession):
    return await create_user(db_session, id=456, username="admin", first_name="Admin")


@pytest.fixture
async def target_user(db_session: AsyncSession):
    return await create_user(db_session, id=555, username="Target", first_name="Target", last_name="User")


@patch("app.bot.handlers.trust.settings")
async def test_trust_by_username_case_insensitive(mock_settings, db_session, admin_user, target_user):
    from app.bot.handlers.trust import trust_user

    mock_settings.BOT_ADMINS = [456]
    msg = _make_message()

    await trust_user(msg, _make_command("tArGeT"), db_session, _make_i18n(), admin_user)

    await db_session.refresh(target_user)
    assert target_user.is_trusted is True


@patch("app.bot.handlers.trust.settings")
async def test_trust_at_prefix_is_stripped(mock_settings, db_session, admin_user, target_user):
    from app.bot.handlers.trust import trust_user

    mock_settings.BOT_ADMINS = [456]
    msg = _make_message()

    await trust_user(msg, _make_command("@target"), db_session, _make_i18n(), admin_user)

    await db_session.refresh(target_user)
    assert target_user.is_trusted is True


@patch("app.bot.handlers.trust.settings")
async def test_trust_ambiguous_username_refused(mock_settings, db_session, admin_user):
    from app.bot.handlers.trust import trust_user

    mock_settings.BOT_ADMINS = [456]
    first = await create_user(db_session, id=601, username="Twin")
    second = await create_user(db_session, id=602, username="twin")

    msg = _make_message()
    i18n = _make_i18n()

    await trust_user(msg, _make_command("twin"), db_session, i18n, admin_user)

    msg.answer.assert_awaited_once_with("Ambiguous username", parse_mode="HTML")
    await db_session.refresh(first)
    await db_session.refresh(second)
    assert first.is_trusted is False
    assert second.is_trusted is False


@patch("app.bot.handlers.trust.settings")
async def test_untrust_ambiguous_username_refused(mock_settings, db_session, admin_user):
    from app.bot.handlers.trust import untrust_user

    mock_settings.BOT_ADMINS = [456]
    await create_user(db_session, id=601, username="Twin", is_trusted=True)
    await create_user(db_session, id=602, username="twin", is_trusted=True)

    msg = _make_message()
    i18n = _make_i18n()

    await untrust_user(msg, _make_command("Twin"), db_session, i18n, admin_user)

    msg.answer.assert_awaited_once_with("Ambiguous username", parse_mode="HTML")


@patch("app.bot.handlers.trust.settings")
async def test_trust_reply_names_user_and_id(mock_settings, db_session, admin_user, target_user):
    from app.bot.handlers.trust import trust_user

    mock_settings.BOT_ADMINS = [456]
    msg = _make_message()
    i18n = _make_i18n()

    await trust_user(msg, _make_command("555"), db_session, i18n, admin_user)

    text = msg.answer.await_args.args[0]
    assert "555" in text
    assert "Target" in text


@patch("app.bot.handlers.trust.settings")
async def test_add_mod_reply_names_user_and_id(mock_settings, db_session, admin_user, target_user):
    from app.bot.handlers.trust import add_mod

    mock_settings.BOT_ADMINS = [456]
    msg = _make_message()
    i18n = _make_i18n()

    await add_mod(msg, _make_command("target"), db_session, i18n, admin_user)

    text = msg.answer.await_args.args[0]
    assert "555" in text
    assert "Target" in text
