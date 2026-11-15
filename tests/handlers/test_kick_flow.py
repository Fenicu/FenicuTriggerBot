"""Кик: не снимать существующий бан и не трогать уже забаненного."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.bot.handlers.chat_moderation import cmd_kick


def _make_i18n() -> MagicMock:
    i18n = MagicMock()
    i18n.mod.error.admin.return_value = "Cannot moderate admin"
    i18n.mod.error.already.banned.return_value = "Already banned"
    i18n.mod.user.kicked.return_value = "User kicked"
    return i18n


def _make_message(target_status: str = "member") -> MagicMock:
    msg = MagicMock()
    msg.chat = MagicMock(id=-1001)
    msg.from_user = MagicMock(id=456)
    msg.chat.get_member = AsyncMock(return_value=MagicMock(status=target_status))
    msg.chat.ban = AsyncMock()
    msg.chat.unban = AsyncMock()
    msg.answer = AsyncMock(return_value=MagicMock(message_id=42))
    msg.reply_to_message = MagicMock()
    msg.reply_to_message.sender_chat = None
    msg.reply_to_message.is_automatic_forward = False
    msg.reply_to_message.forum_topic_created = None
    msg.reply_to_message.from_user = MagicMock(id=555, full_name="Target")
    return msg


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_kick_refuses_already_banned(mock_autodel: AsyncMock) -> None:
    msg = _make_message(target_status="kicked")
    db_chat = MagicMock(autodelete_settings=None)

    await cmd_kick(msg, db_chat, _make_i18n())

    msg.chat.ban.assert_not_awaited()
    msg.chat.unban.assert_not_awaited()
    msg.answer.assert_awaited_once_with("Already banned", parse_mode="HTML")


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_kick_bans_then_unbans_only_if_banned(mock_autodel: AsyncMock) -> None:
    msg = _make_message(target_status="member")
    db_chat = MagicMock(autodelete_settings=None)

    await cmd_kick(msg, db_chat, _make_i18n())

    msg.chat.ban.assert_awaited_once()
    assert msg.chat.ban.call_args.kwargs["user_id"] == 555
    msg.chat.unban.assert_awaited_once_with(user_id=555, only_if_banned=True)

    calls = [name for name, _args, _kwargs in msg.chat.method_calls]
    assert calls.index("ban") < calls.index("unban")
