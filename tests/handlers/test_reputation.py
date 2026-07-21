"""Tests for app/bot/handlers/reputation.py — /status, /tag, /deltag commands."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user_chat import UserChat
from tests.factories import create_chat, create_user


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_i18n():
    i18n = MagicMock()
    i18n.reputation.group.only.return_value = "Groups only"
    i18n.reputation.disabled.return_value = "Reputation disabled"
    i18n.reputation.no.data.return_value = "No data"
    i18n.reputation.status.return_value = "Status text"
    i18n.reputation.next.level.return_value = "10 until next"
    i18n.reputation.max.level.return_value = "Max level!"
    i18n.error.no.rights.return_value = "No rights"
    i18n.tag.usage.return_value = "Usage: /tag <text>"
    i18n.tag.reply.required.return_value = "Reply required"
    i18n.tag.invalid.return_value = "Invalid tag"
    i18n.tag.set.return_value = "Tag set"
    i18n.tag.cleared.return_value = "Tag cleared"
    i18n.user.missing.return_value = "User not found"
    i18n.error.unknown.return_value = "Unknown error"
    return i18n


def _make_command(args=None):
    cmd = MagicMock()
    cmd.args = args
    return cmd


def _make_message(
    chat_id=-100123, user_id=456, text="/status", chat_type="supergroup", member_status="member", reply_user=None
):
    msg = MagicMock()
    msg.chat = MagicMock(id=chat_id, type=chat_type)
    msg.from_user = MagicMock(id=user_id, username="testuser", full_name="Test User")
    msg.from_user.mention_html.return_value = "<b>Test User</b>"
    msg.text = text
    msg.answer = AsyncMock()
    msg.ephemeral_message_id = None

    member = MagicMock()
    member.status = member_status
    msg.chat.get_member = AsyncMock(return_value=member)

    if reply_user:
        msg.reply_to_message = MagicMock()
        msg.reply_to_message.from_user = reply_user
    else:
        msg.reply_to_message = None

    return msg


def _make_target_user(user_id=999, full_name="Target"):
    user = MagicMock()
    user.id = user_id
    user.full_name = full_name
    user.username = "target"
    user.mention_html.return_value = f"<b>{full_name}</b>"
    return user


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def chat(db_session: AsyncSession):
    return await create_chat(db_session, tags_enabled=True)


@pytest.fixture
async def chat_tags_disabled(db_session: AsyncSession):
    return await create_chat(db_session, tags_enabled=False)


@pytest.fixture
async def user(db_session: AsyncSession):
    return await create_user(db_session)


# ── /status ───────────────────────────────────────────────────────────────────


async def test_status_private_chat(db_session, chat, monkeypatch):
    from app.bot.handlers.reputation import status_command

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr("app.bot.handlers.reputation.bot", mock_bot)

    msg = _make_message(chat_type="private")
    i18n = _make_i18n()

    await status_command(msg, db_session, i18n, chat)

    mock_bot.send_message.assert_awaited_once_with(chat_id=msg.chat.id, text="Groups only", parse_mode="HTML")


async def test_status_tags_disabled(db_session, chat_tags_disabled, monkeypatch):
    from app.bot.handlers.reputation import status_command

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr("app.bot.handlers.reputation.bot", mock_bot)

    msg = _make_message()
    i18n = _make_i18n()

    await status_command(msg, db_session, i18n, chat_tags_disabled)

    mock_bot.send_message.assert_awaited_once()
    _, kwargs = mock_bot.send_message.call_args
    assert kwargs["text"] == "Reputation disabled"
    assert kwargs["receiver_user_id"] == msg.from_user.id


async def test_status_no_user_chat(db_session, chat, monkeypatch):
    from app.bot.handlers.reputation import status_command

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr("app.bot.handlers.reputation.bot", mock_bot)

    msg = _make_message(chat_id=chat.id, user_id=456)
    i18n = _make_i18n()

    await status_command(msg, db_session, i18n, chat)

    mock_bot.send_message.assert_awaited_once()
    _, kwargs = mock_bot.send_message.call_args
    assert kwargs["text"] == "No data"
    assert kwargs["receiver_user_id"] == 456


async def test_status_success(db_session, chat, user, monkeypatch):
    from app.bot.handlers.reputation import status_command

    # Create a UserChat entry
    uc = UserChat(user_id=user.id, chat_id=chat.id, reputation_score=100, reputation_level=1)
    db_session.add(uc)
    await db_session.flush()

    mock_bot = MagicMock()
    mock_bot.send_message = AsyncMock(return_value=MagicMock())
    monkeypatch.setattr("app.bot.handlers.reputation.bot", mock_bot)

    msg = _make_message(chat_id=chat.id, user_id=user.id)
    i18n = _make_i18n()

    await status_command(msg, db_session, i18n, chat)

    mock_bot.send_message.assert_awaited_once()
    _, kwargs = mock_bot.send_message.call_args
    assert kwargs["text"] == "Status text"
    assert kwargs["receiver_user_id"] == user.id


# ── /tag ──────────────────────────────────────────────────────────────────────


async def test_tag_private_chat(db_session, chat):
    from app.bot.handlers.reputation import tag_command

    msg = _make_message(chat_type="private", member_status="administrator")
    i18n = _make_i18n()

    await tag_command(msg, _make_command("test"), db_session, i18n, chat)

    msg.answer.assert_not_awaited()


async def test_tag_not_admin(db_session, chat):
    from app.bot.handlers.reputation import tag_command

    msg = _make_message(member_status="member")
    i18n = _make_i18n()

    await tag_command(msg, _make_command("test"), db_session, i18n, chat)

    msg.answer.assert_awaited_once_with("No rights", parse_mode="HTML")


async def test_tag_no_args(db_session, chat):
    from app.bot.handlers.reputation import tag_command

    msg = _make_message(member_status="administrator")
    i18n = _make_i18n()

    await tag_command(msg, _make_command(None), db_session, i18n, chat)

    msg.answer.assert_awaited_once_with("Usage: /tag <text>", parse_mode="HTML")


async def test_tag_no_reply(db_session, chat):
    from app.bot.handlers.reputation import tag_command

    msg = _make_message(member_status="administrator")
    i18n = _make_i18n()

    await tag_command(msg, _make_command("MyTag"), db_session, i18n, chat)

    msg.answer.assert_awaited_once_with("Reply required", parse_mode="HTML")


async def test_tag_invalid_chars(db_session, chat):
    from app.bot.handlers.reputation import tag_command

    target = _make_target_user()
    msg = _make_message(member_status="administrator", reply_user=target)
    i18n = _make_i18n()

    await tag_command(msg, _make_command("tag<script>"), db_session, i18n, chat)

    msg.answer.assert_awaited_once_with("Invalid tag", parse_mode="HTML")


async def test_tag_user_not_in_chat(db_session, chat):
    from app.bot.handlers.reputation import tag_command

    target = _make_target_user(user_id=999)
    msg = _make_message(chat_id=chat.id, member_status="administrator", reply_user=target)
    i18n = _make_i18n()

    await tag_command(msg, _make_command("GoodTag"), db_session, i18n, chat)

    msg.answer.assert_awaited_once_with("User not found", parse_mode="HTML")


@patch("app.bot.handlers.reputation.set_manual_tag", new_callable=AsyncMock)
async def test_tag_success(mock_set_tag, db_session, chat, user):
    from app.bot.handlers.reputation import tag_command

    uc = UserChat(user_id=user.id, chat_id=chat.id)
    db_session.add(uc)
    await db_session.flush()

    target = _make_target_user(user_id=user.id)
    msg = _make_message(chat_id=chat.id, member_status="administrator", reply_user=target)
    i18n = _make_i18n()

    mock_set_tag.return_value = True

    await tag_command(msg, _make_command("Elite"), db_session, i18n, chat)

    mock_set_tag.assert_awaited_once()
    msg.answer.assert_awaited_once_with("Tag set", parse_mode="HTML")


# ── /deltag ───────────────────────────────────────────────────────────────────


async def test_deltag_not_admin(db_session, chat):
    from app.bot.handlers.reputation import deltag_command

    msg = _make_message(member_status="member")
    i18n = _make_i18n()

    await deltag_command(msg, db_session, i18n, chat)

    msg.answer.assert_awaited_once_with("No rights", parse_mode="HTML")


async def test_deltag_no_reply(db_session, chat):
    from app.bot.handlers.reputation import deltag_command

    msg = _make_message(member_status="administrator")
    i18n = _make_i18n()

    await deltag_command(msg, db_session, i18n, chat)

    msg.answer.assert_awaited_once_with("Reply required", parse_mode="HTML")


@patch("app.bot.handlers.reputation.clear_manual_tag", new_callable=AsyncMock)
async def test_deltag_success(mock_clear, db_session, chat, user):
    from app.bot.handlers.reputation import deltag_command

    uc = UserChat(user_id=user.id, chat_id=chat.id, tag="Custom", tag_is_manual=True)
    db_session.add(uc)
    await db_session.flush()

    target = _make_target_user(user_id=user.id)
    msg = _make_message(chat_id=chat.id, member_status="administrator", reply_user=target)
    i18n = _make_i18n()

    mock_clear.return_value = True

    await deltag_command(msg, db_session, i18n, chat)

    mock_clear.assert_awaited_once()
    msg.answer.assert_awaited_once_with("Tag cleared", parse_mode="HTML")


# ── _make_progress_bar ────────────────────────────────────────────────────────


async def test_progress_bar_zero():
    from app.bot.handlers.reputation import _make_progress_bar

    bar = _make_progress_bar(0)
    assert bar.count("\u2591") == 12  # all empty
    assert bar.count("\u2588") == 0


async def test_progress_bar_full():
    from app.bot.handlers.reputation import _make_progress_bar

    bar = _make_progress_bar(100)
    assert bar.count("\u2588") == 12  # all filled
    assert bar.count("\u2591") == 0


async def test_progress_bar_half():
    from app.bot.handlers.reputation import _make_progress_bar

    bar = _make_progress_bar(50, length=10)
    assert bar.count("\u2588") == 5
    assert bar.count("\u2591") == 5
