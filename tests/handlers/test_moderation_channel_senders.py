"""Команды модерации для сообщений от имени канала/чата и автопересланных из связанного канала."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.bot.handlers.chat_moderation import (
    cmd_ban,
    cmd_kick,
    cmd_mute,
    cmd_unban,
    cmd_warn,
)

CHAT_ID = -1001
CHANNEL_ID = -100777


def _make_i18n() -> MagicMock:
    i18n = MagicMock()
    i18n.mod.error.admin.return_value = "Cannot moderate admin"
    i18n.mod.error.channel.target.return_value = "Channel target"
    i18n.mod.user.banned.return_value = "User banned"
    i18n.mod.user.unbanned.return_value = "User unbanned"
    i18n.mod.user.muted.return_value = "User muted"
    i18n.mod.user.kicked.return_value = "User kicked"
    i18n.mod.user.channel.banned.return_value = "Channel banned"
    i18n.mod.user.channel.unbanned.return_value = "Channel unbanned"
    i18n.mod.warn.added.return_value = "Warn added"
    return i18n


def _make_message(*, sender_chat_id: int | None = CHANNEL_ID, is_automatic_forward: bool = False) -> MagicMock:
    msg = MagicMock()
    msg.chat = MagicMock(id=CHAT_ID)
    msg.from_user = MagicMock(id=456)
    msg.chat.ban = AsyncMock()
    msg.chat.unban = AsyncMock()
    msg.chat.restrict = AsyncMock()
    msg.chat.ban_sender_chat = AsyncMock()
    msg.chat.unban_sender_chat = AsyncMock()
    msg.chat.get_member = AsyncMock(return_value=MagicMock(status="member"))
    msg.answer = AsyncMock(return_value=MagicMock(message_id=42))

    reply = MagicMock()
    reply.sender_chat = MagicMock(id=sender_chat_id, title="Channel") if sender_chat_id is not None else None
    reply.is_automatic_forward = is_automatic_forward
    reply.forum_topic_created = None
    reply.from_user = MagicMock(id=555, full_name="Target")
    msg.reply_to_message = reply
    return msg


def _make_command(args: str | None = None) -> MagicMock:
    cmd = MagicMock()
    cmd.args = args
    return cmd


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_ban_acts_on_sender_chat(mock_autodel: AsyncMock) -> None:
    msg = _make_message()
    db_chat = MagicMock(autodelete_settings=None)

    await cmd_ban(msg, _make_command(), db_chat, _make_i18n())

    msg.chat.ban_sender_chat.assert_awaited_once_with(sender_chat_id=CHANNEL_ID)
    msg.chat.ban.assert_not_awaited()
    msg.answer.assert_awaited_once()


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_ban_automatic_forward_acts_on_linked_channel(mock_autodel: AsyncMock) -> None:
    msg = _make_message(is_automatic_forward=True)
    db_chat = MagicMock(autodelete_settings=None)

    await cmd_ban(msg, _make_command(), db_chat, _make_i18n())

    msg.chat.ban_sender_chat.assert_awaited_once_with(sender_chat_id=CHANNEL_ID)


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_unban_acts_on_sender_chat(mock_autodel: AsyncMock) -> None:
    msg = _make_message()
    db_chat = MagicMock(autodelete_settings=None)

    await cmd_unban(msg, _make_command(), db_chat, _make_i18n())

    msg.chat.unban_sender_chat.assert_awaited_once_with(sender_chat_id=CHANNEL_ID)
    msg.chat.unban.assert_not_awaited()


@pytest.mark.parametrize("command", ["mute", "kick", "warn"])
async def test_refuses_channel_target(command: str) -> None:
    msg = _make_message()
    i18n = _make_i18n()
    db_chat = MagicMock(autodelete_settings=None, warn_limit=3)

    if command == "mute":
        await cmd_mute(msg, _make_command("10m"), db_chat, i18n)
        msg.chat.restrict.assert_not_awaited()
    elif command == "kick":
        await cmd_kick(msg, db_chat, i18n)
        msg.chat.ban.assert_not_awaited()
    else:
        with patch("app.bot.handlers.chat_moderation.ModerationService") as service:
            await cmd_warn(msg, _make_command("spam"), MagicMock(), db_chat, i18n)
        service.assert_not_called()

    msg.answer.assert_awaited_once_with("Channel target", parse_mode="HTML")


@pytest.mark.parametrize("command", ["mute", "kick", "warn"])
async def test_refuses_automatic_forward(command: str) -> None:
    msg = _make_message(is_automatic_forward=True)
    i18n = _make_i18n()
    db_chat = MagicMock(autodelete_settings=None, warn_limit=3)

    if command == "mute":
        await cmd_mute(msg, _make_command("10m"), db_chat, i18n)
        msg.chat.restrict.assert_not_awaited()
    elif command == "kick":
        await cmd_kick(msg, db_chat, i18n)
        msg.chat.ban.assert_not_awaited()
    else:
        with patch("app.bot.handlers.chat_moderation.ModerationService") as service:
            await cmd_warn(msg, _make_command("spam"), MagicMock(), db_chat, i18n)
        service.assert_not_called()

    msg.answer.assert_awaited_once_with("Channel target", parse_mode="HTML")
