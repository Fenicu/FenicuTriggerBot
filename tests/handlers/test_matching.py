"""Tests for app/bot/handlers/matching.py — trigger matching on incoming messages."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.trigger import AccessLevel, ModerationStatus
from tests.factories import create_chat, create_trigger, create_user


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_message(chat_id=-100123, user_id=456, text="hello", member_status="member"):
    msg = MagicMock()
    msg.chat = MagicMock(id=chat_id, type="supergroup")
    msg.from_user = MagicMock(id=user_id, username="testuser", full_name="Test User")
    msg.text = text
    msg.bot = MagicMock()
    msg.bot.send_dice = AsyncMock()

    member = MagicMock()
    member.status = member_status
    msg.chat.get_member = AsyncMock(return_value=member)

    return msg


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def chat(db_session: AsyncSession):
    return await create_chat(db_session, module_triggers=True)


@pytest.fixture
async def user(db_session: AsyncSession):
    return await create_user(db_session)


# ── _check_access ─────────────────────────────────────────────────────────────


async def test_check_access_all():
    from app.bot.handlers.matching import _check_access

    trigger = MagicMock()
    trigger.access_level = AccessLevel.ALL
    msg = _make_message()

    assert await _check_access(trigger, msg) is True


async def test_check_access_admins_allowed():
    from app.bot.handlers.matching import _check_access

    trigger = MagicMock()
    trigger.access_level = AccessLevel.ADMINS
    msg = _make_message(member_status="administrator")

    assert await _check_access(trigger, msg) is True


async def test_check_access_admins_denied():
    from app.bot.handlers.matching import _check_access

    trigger = MagicMock()
    trigger.access_level = AccessLevel.ADMINS
    msg = _make_message(member_status="member")

    assert await _check_access(trigger, msg) is False


async def test_check_access_owner_allowed():
    from app.bot.handlers.matching import _check_access

    trigger = MagicMock()
    trigger.access_level = AccessLevel.OWNER
    msg = _make_message(member_status="creator")

    assert await _check_access(trigger, msg) is True


async def test_check_access_owner_denied_for_admin():
    from app.bot.handlers.matching import _check_access

    trigger = MagicMock()
    trigger.access_level = AccessLevel.OWNER
    msg = _make_message(member_status="administrator")

    assert await _check_access(trigger, msg) is False


# ── check_triggers ────────────────────────────────────────────────────────────


async def test_check_triggers_no_text(db_session, chat):
    from app.bot.handlers.matching import check_triggers

    msg = _make_message(chat_id=chat.id, text=None)
    # Should return early without error
    await check_triggers(msg, db_session, chat)


async def test_check_triggers_module_disabled(db_session):
    from app.bot.handlers.matching import check_triggers

    chat = await create_chat(db_session, module_triggers=False)
    msg = _make_message(chat_id=chat.id, text="hello")

    # Should return early
    await check_triggers(msg, db_session, chat)


async def test_check_triggers_no_triggers_in_chat(db_session, chat):
    from app.bot.handlers.matching import check_triggers

    msg = _make_message(chat_id=chat.id, text="hello")

    with patch("app.bot.handlers.matching.get_triggers_by_chat", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = []
        await check_triggers(msg, db_session, chat)


async def test_check_triggers_no_match(db_session, chat, user):
    from app.bot.handlers.matching import check_triggers

    await create_trigger(db_session, chat.id, user.id, key_phrase="goodbye")
    await db_session.commit()

    msg = _make_message(chat_id=chat.id, text="hello")

    with patch("app.bot.handlers.matching.get_triggers_by_chat", new_callable=AsyncMock) as mock_get:
        from app.db.models.trigger import MatchType, Trigger
        t = MagicMock(spec=Trigger)
        t.key_phrase = "goodbye"
        t.match_type = MatchType.EXACT
        t.is_case_sensitive = False
        t.access_level = AccessLevel.ALL
        t.moderation_status = ModerationStatus.SAFE
        mock_get.return_value = [t]

        with patch("app.bot.handlers.matching.find_matches", new_callable=AsyncMock) as mock_find:
            mock_find.return_value = []
            await check_triggers(msg, db_session, chat)


@patch("app.bot.handlers.matching._send_trigger_message", new_callable=AsyncMock)
@patch("app.bot.handlers.matching._prepare_content", new_callable=AsyncMock)
@patch("app.bot.handlers.matching.find_matches", new_callable=AsyncMock)
@patch("app.bot.handlers.matching.get_triggers_by_chat", new_callable=AsyncMock)
async def test_check_triggers_match_sends_response(
    mock_get_triggers, mock_find, mock_prepare, mock_send, db_session, chat
):
    from app.bot.handlers.matching import check_triggers

    trigger = MagicMock()
    trigger.access_level = AccessLevel.ALL
    trigger.content = {"text": "Hello!"}
    trigger.is_template = False

    mock_get_triggers.return_value = [trigger]
    mock_find.return_value = [trigger]
    mock_prepare.return_value = {}

    msg = _make_message(chat_id=chat.id, text="test_key")
    await check_triggers(msg, db_session, chat)

    mock_send.assert_awaited_once()


@patch("app.bot.handlers.matching._send_trigger_message", new_callable=AsyncMock)
@patch("app.bot.handlers.matching._prepare_content", new_callable=AsyncMock)
@patch("app.bot.handlers.matching.find_matches", new_callable=AsyncMock)
@patch("app.bot.handlers.matching.get_triggers_by_chat", new_callable=AsyncMock)
async def test_check_triggers_access_denied_skipped(
    mock_get_triggers, mock_find, mock_prepare, mock_send, db_session, chat
):
    from app.bot.handlers.matching import check_triggers

    trigger = MagicMock()
    trigger.access_level = AccessLevel.ADMINS
    trigger.content = {"text": "Admin only"}
    trigger.is_template = False

    mock_get_triggers.return_value = [trigger]
    mock_find.return_value = [trigger]

    msg = _make_message(chat_id=chat.id, text="test", member_status="member")
    await check_triggers(msg, db_session, chat)

    mock_send.assert_not_awaited()


# ── _get_timezone ─────────────────────────────────────────────────────────────


async def test_get_timezone_valid():
    from app.bot.handlers.matching import _get_timezone
    from zoneinfo import ZoneInfo

    tz = _get_timezone("Europe/Moscow")
    assert tz == ZoneInfo("Europe/Moscow")


async def test_get_timezone_invalid_falls_back():
    from app.bot.handlers.matching import _get_timezone

    tz = _get_timezone("Invalid/Zone")
    # Should return default timezone without raising
    assert tz is not None


async def test_get_timezone_none_falls_back():
    from app.bot.handlers.matching import _get_timezone

    tz = _get_timezone(None)
    assert tz is not None
