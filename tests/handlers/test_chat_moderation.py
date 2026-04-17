"""Tests for app/bot/handlers/chat_moderation.py — moderation commands."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import create_chat, create_user, create_warn


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_i18n():
    i18n = MagicMock()
    i18n.mod.error.admin.return_value = "Cannot moderate admin"
    i18n.mod.user.banned.return_value = "User banned"
    i18n.mod.user.muted.return_value = "User muted"
    i18n.mod.user.unbanned.return_value = "User unbanned"
    i18n.mod.user.unmuted.return_value = "User unmuted"
    i18n.mod.user.kicked.return_value = "User kicked"
    i18n.mod.warn.added.return_value = "Warn added"
    i18n.mod.warn.removed.return_value = "Warn removed"
    i18n.mod.warn.reset.return_value = "Warns reset"
    i18n.mod.warns.list.return_value = "Warns list"
    i18n.warns.none.return_value = "No warns"
    i18n.warns.none.user.return_value = "No warns for user"
    i18n.punishment.ban.return_value = "ban"
    i18n.punishment.mute.return_value = "mute"
    return i18n


def _make_command(args=None):
    cmd = MagicMock()
    cmd.args = args
    return cmd


def _make_target_user(user_id=999, full_name="Target User"):
    user = MagicMock()
    user.id = user_id
    user.full_name = full_name
    user.username = "target"
    return user


def _make_message(chat_id=-100123, user_id=456, reply_user=None, member_status="member"):
    msg = MagicMock()
    msg.chat = MagicMock(id=chat_id, type="supergroup")
    msg.from_user = MagicMock(id=user_id, username="testmod", full_name="Test Mod")

    sent = MagicMock()
    sent.message_id = 42
    msg.answer = AsyncMock(return_value=sent)

    if reply_user:
        msg.reply_to_message = MagicMock()
        msg.reply_to_message.from_user = reply_user
    else:
        msg.reply_to_message = None

    member = MagicMock()
    member.status = member_status
    msg.chat.get_member = AsyncMock(return_value=member)
    msg.chat.ban = AsyncMock()
    msg.chat.unban = AsyncMock()
    msg.chat.restrict = AsyncMock()

    return msg


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def chat(db_session: AsyncSession):
    return await create_chat(db_session, module_moderation=True)


# ── parse_args ────────────────────────────────────────────────────────────────


async def test_parse_args_none():
    from app.bot.handlers.chat_moderation import parse_args

    duration, reason = parse_args(None)
    assert duration is None
    assert reason is None


async def test_parse_args_time_only():
    from app.bot.handlers.chat_moderation import parse_args

    duration, reason = parse_args("10m")
    assert duration == 600
    assert reason is None


async def test_parse_args_time_and_reason():
    from app.bot.handlers.chat_moderation import parse_args

    duration, reason = parse_args("2h spam")
    assert duration == 7200
    assert reason == "spam"


async def test_parse_args_reason_only():
    from app.bot.handlers.chat_moderation import parse_args

    duration, reason = parse_args("being rude")
    assert duration is None
    assert reason == "being rude"


# ── get_target_user ───────────────────────────────────────────────────────────


async def test_get_target_user_no_reply():
    from app.bot.handlers.chat_moderation import get_target_user

    msg = _make_message()
    user_id, user_name = await get_target_user(msg)
    assert user_id is None
    assert user_name is None


async def test_get_target_user_with_reply():
    from app.bot.handlers.chat_moderation import get_target_user

    target = _make_target_user(user_id=777, full_name="John")
    msg = _make_message(reply_user=target)
    user_id, user_name = await get_target_user(msg)
    assert user_id == 777
    assert user_name == "John"


# ── cmd_ban ───────────────────────────────────────────────────────────────────


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_ban_no_reply(mock_autodel):
    from app.bot.handlers.chat_moderation import cmd_ban

    msg = _make_message()
    db_chat = MagicMock(autodelete_settings=None)
    await cmd_ban(msg, _make_command(), db_chat, _make_i18n())
    msg.answer.assert_not_awaited()


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_ban_admin_target_rejected(mock_autodel):
    from app.bot.handlers.chat_moderation import cmd_ban

    target = _make_target_user()
    msg = _make_message(reply_user=target, member_status="administrator")
    i18n = _make_i18n()
    db_chat = MagicMock(autodelete_settings=None)

    await cmd_ban(msg, _make_command(), db_chat, i18n)
    msg.answer.assert_awaited_once_with("Cannot moderate admin", parse_mode="HTML")
    msg.chat.ban.assert_not_awaited()


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_ban_success(mock_autodel):
    from app.bot.handlers.chat_moderation import cmd_ban

    target = _make_target_user(user_id=999)
    msg = _make_message(reply_user=target)
    db_chat = MagicMock(autodelete_settings=None)

    await cmd_ban(msg, _make_command("1h spam"), db_chat, _make_i18n())
    msg.chat.ban.assert_awaited_once()
    call_kwargs = msg.chat.ban.call_args.kwargs
    assert call_kwargs["user_id"] == 999
    assert call_kwargs["until_date"] is not None


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_ban_permanent(mock_autodel):
    from app.bot.handlers.chat_moderation import cmd_ban

    target = _make_target_user()
    msg = _make_message(reply_user=target)
    db_chat = MagicMock(autodelete_settings=None)

    await cmd_ban(msg, _make_command(None), db_chat, _make_i18n())
    call_kwargs = msg.chat.ban.call_args.kwargs
    assert call_kwargs["until_date"] is None


# ── cmd_mute ──────────────────────────────────────────────────────────────────


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_mute_success(mock_autodel):
    from app.bot.handlers.chat_moderation import cmd_mute

    target = _make_target_user()
    msg = _make_message(reply_user=target)
    db_chat = MagicMock(autodelete_settings=None)

    await cmd_mute(msg, _make_command("30m flooding"), db_chat, _make_i18n())
    msg.chat.restrict.assert_awaited_once()
    call_kwargs = msg.chat.restrict.call_args.kwargs
    assert call_kwargs["user_id"] == 999
    assert call_kwargs["permissions"].can_send_messages is False


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_mute_admin_rejected(mock_autodel):
    from app.bot.handlers.chat_moderation import cmd_mute

    target = _make_target_user()
    msg = _make_message(reply_user=target, member_status="creator")
    db_chat = MagicMock(autodelete_settings=None)

    await cmd_mute(msg, _make_command(), db_chat, _make_i18n())
    msg.chat.restrict.assert_not_awaited()


# ── cmd_unban ─────────────────────────────────────────────────────────────────


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_unban_by_reply(mock_autodel):
    from app.bot.handlers.chat_moderation import cmd_unban

    target = _make_target_user(user_id=888)
    msg = _make_message(reply_user=target)
    db_chat = MagicMock(autodelete_settings=None)

    await cmd_unban(msg, _make_command(), db_chat, _make_i18n())
    msg.chat.unban.assert_awaited_once_with(user_id=888, only_if_banned=True)


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_unban_by_user_id_arg(mock_autodel):
    from app.bot.handlers.chat_moderation import cmd_unban

    msg = _make_message()  # no reply
    db_chat = MagicMock(autodelete_settings=None)

    await cmd_unban(msg, _make_command("12345"), db_chat, _make_i18n())
    msg.chat.unban.assert_awaited_once_with(user_id=12345, only_if_banned=True)


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_unban_no_target(mock_autodel):
    from app.bot.handlers.chat_moderation import cmd_unban

    msg = _make_message()
    db_chat = MagicMock(autodelete_settings=None)

    await cmd_unban(msg, _make_command(None), db_chat, _make_i18n())
    msg.chat.unban.assert_not_awaited()


# ── cmd_unmute ────────────────────────────────────────────────────────────────


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_unmute_success(mock_autodel):
    from app.bot.handlers.chat_moderation import cmd_unmute

    target = _make_target_user()
    msg = _make_message(reply_user=target)
    db_chat = MagicMock(autodelete_settings=None)

    await cmd_unmute(msg, db_chat, _make_i18n())
    msg.chat.restrict.assert_awaited_once()
    perms = msg.chat.restrict.call_args.kwargs["permissions"]
    assert perms.can_send_messages is True


# ── cmd_kick ──────────────────────────────────────────────────────────────────


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_kick_success(mock_autodel):
    from app.bot.handlers.chat_moderation import cmd_kick

    target = _make_target_user(user_id=555)
    msg = _make_message(reply_user=target)
    db_chat = MagicMock(autodelete_settings=None)

    await cmd_kick(msg, db_chat, _make_i18n())
    # kick does unban, ban, unban
    assert msg.chat.unban.await_count == 2
    assert msg.chat.ban.await_count == 1


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_kick_admin_rejected(mock_autodel):
    from app.bot.handlers.chat_moderation import cmd_kick

    target = _make_target_user()
    msg = _make_message(reply_user=target, member_status="administrator")
    db_chat = MagicMock(autodelete_settings=None)

    await cmd_kick(msg, db_chat, _make_i18n())
    msg.answer.assert_awaited_once_with("Cannot moderate admin", parse_mode="HTML")


# ── cmd_warn (DB integration) ────────────────────────────────────────────────


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_warn_adds_warn(mock_autodel, db_session, chat):
    from app.bot.handlers.chat_moderation import cmd_warn

    user = await create_user(db_session, id=456)
    target_db = await create_user(db_session, id=999, first_name="Target")
    target = _make_target_user(user_id=target_db.id)
    msg = _make_message(chat_id=chat.id, user_id=user.id, reply_user=target)
    db_chat = chat

    await cmd_warn(msg, _make_command("spamming"), db_session, db_chat, _make_i18n())
    msg.answer.assert_awaited()

    from app.services.moderation_service import ModerationService

    svc = ModerationService(db_session)
    count = await svc.get_warn_count(chat.id, target_db.id)
    assert count == 1


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_warn_triggers_punishment_on_limit(mock_autodel, db_session, chat):
    from app.bot.handlers.chat_moderation import cmd_warn

    user = await create_user(db_session, id=456)
    target_db = await create_user(db_session, id=999, first_name="Target")
    # Pre-fill warns up to limit - 1
    for _ in range(chat.warn_limit - 1):
        await create_warn(db_session, chat.id, target_db.id, admin_id=user.id)
    await db_session.commit()

    target = _make_target_user(user_id=target_db.id)
    msg = _make_message(chat_id=chat.id, user_id=user.id, reply_user=target)

    await cmd_warn(msg, _make_command("final"), db_session, chat, _make_i18n())
    # Should have applied ban punishment (default is "ban")
    msg.chat.ban.assert_awaited_once()


# ── cmd_warns ─────────────────────────────────────────────────────────────────


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_warns_self_no_warns(mock_autodel, db_session, chat):
    from app.bot.handlers.chat_moderation import cmd_warns

    msg = _make_message(chat_id=chat.id)
    i18n = _make_i18n()
    await cmd_warns(msg, db_session, chat, i18n)
    msg.answer.assert_awaited_once_with("No warns for user", parse_mode="HTML")


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_warns_list_existing(mock_autodel, db_session, chat):
    from app.bot.handlers.chat_moderation import cmd_warns

    user = await create_user(db_session)
    await create_warn(db_session, chat.id, user.id, admin_id=user.id, reason="test reason")
    await db_session.commit()

    target = _make_target_user(user_id=user.id, full_name="Test Mod")
    msg = _make_message(chat_id=chat.id, reply_user=target)
    i18n = _make_i18n()

    await cmd_warns(msg, db_session, chat, i18n)
    msg.answer.assert_awaited_once()
    # It called i18n.mod.warns.list, which returns "Warns list"
    assert msg.answer.call_args.args[0] == "Warns list"
