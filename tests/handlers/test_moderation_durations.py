"""Длительности наказаний: лимит 366 дней и защита от переполнения timedelta."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.bot.handlers.chat_moderation import build_until_date, cmd_ban, cmd_mute

MAX_SECONDS = 366 * 86400


def _make_i18n() -> MagicMock:
    i18n = MagicMock()
    i18n.mod.error.admin.return_value = "Cannot moderate admin"
    i18n.mod.error.duration.too.long.return_value = "Too long"
    i18n.mod.user.banned.return_value = "User banned"
    i18n.mod.user.muted.return_value = "User muted"
    return i18n


def _make_message() -> MagicMock:
    msg = MagicMock()
    msg.chat = MagicMock(id=-1001)
    msg.from_user = MagicMock(id=456)
    msg.chat.get_member = AsyncMock(return_value=MagicMock(status="member"))
    msg.chat.ban = AsyncMock()
    msg.chat.restrict = AsyncMock()
    msg.answer = AsyncMock(return_value=MagicMock(message_id=42))
    reply = MagicMock()
    reply.sender_chat = None
    reply.is_automatic_forward = False
    reply.forum_topic_created = None
    reply.from_user = MagicMock(id=555, full_name="Target")
    msg.reply_to_message = reply
    return msg


def _make_command(args: str | None) -> MagicMock:
    cmd = MagicMock()
    cmd.args = args
    return cmd


def test_until_date_none_for_permanent() -> None:
    assert build_until_date(None) is None


def test_until_date_accepts_limit() -> None:
    assert build_until_date(MAX_SECONDS) is not None


@pytest.mark.parametrize("duration", [MAX_SECONDS + 1, 10**30])
def test_until_date_rejects_too_long(duration: int) -> None:
    with pytest.raises(ValueError):
        build_until_date(duration)


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_ban_rejects_too_long_duration(mock_autodel: AsyncMock) -> None:
    msg = _make_message()

    await cmd_ban(msg, _make_command("400d"), MagicMock(autodelete_settings=None), _make_i18n())

    msg.chat.ban.assert_not_awaited()
    msg.answer.assert_awaited_once_with("Too long", parse_mode="HTML")


@patch("app.bot.handlers.chat_moderation.schedule_autodelete", new_callable=AsyncMock)
async def test_mute_rejects_huge_duration_without_crashing(mock_autodel: AsyncMock) -> None:
    msg = _make_message()

    await cmd_mute(
        msg,
        _make_command("999999999999999999999w"),
        MagicMock(autodelete_settings=None),
        _make_i18n(),
    )

    msg.chat.restrict.assert_not_awaited()
    msg.answer.assert_awaited_once_with("Too long", parse_mode="HTML")
