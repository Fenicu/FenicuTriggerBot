"""Tests for app/bot/handlers/matching.py — trigger matching on incoming messages."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
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


# ── _render_template_field truncation ─────────────────────────────────────────


def test_render_template_field_truncates_to_limit():
    """После рендера длинного шаблона значение должно быть обрезано до max_len с эллипсисом."""
    from app.bot.handlers.matching import _render_template_field

    content = {"caption": "x" * 2000}
    _render_template_field(content, "caption", context={}, trigger_id=1, max_len=1024)

    assert len(content["caption"]) == 1024
    assert content["caption"].endswith("…")


def test_render_template_field_no_truncate_when_under_limit():
    from app.bot.handlers.matching import _render_template_field

    content = {"caption": "short"}
    _render_template_field(content, "caption", context={}, trigger_id=1, max_len=1024)

    assert content["caption"] == "short"


def test_render_template_field_no_max_len_keeps_full_length():
    """Backward compat: вызов без max_len не обрезает."""
    from app.bot.handlers.matching import _render_template_field

    content = {"text": "y" * 5000}
    _render_template_field(content, "text", context={}, trigger_id=1)

    assert len(content["text"]) == 5000


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


# ── _send_trigger_message ─────────────────────────────────────────────────────


def _send_message_content():
    """Минимальный валидный dict для Message.model_validate без media."""
    return {
        "message_id": 1,
        "date": 0,
        "chat": {"id": -100, "type": "supergroup", "title": "t"},
        "text": "hi",
    }


def _send_message():
    msg = MagicMock()
    msg.chat = MagicMock(id=-100)
    msg.bot = MagicMock()
    msg.bot.send_dice = AsyncMock()
    return msg


async def test_send_trigger_skips_when_permission_cached_missing():
    from app.bot.handlers import matching

    trigger = MagicMock(id=42)
    msg = _send_message()
    session = AsyncMock()

    with (
        patch.object(matching.permissions, "is_missing", new=AsyncMock(return_value=True)),
        patch("app.bot.handlers.matching.Message") as mock_message_cls,
        patch("app.bot.handlers.matching.increment_usage", new_callable=AsyncMock) as mock_inc,
    ):
        await matching._send_trigger_message(_send_message_content(), {}, msg, trigger, session)

    mock_message_cls.model_validate.assert_not_called()
    mock_inc.assert_not_awaited()


async def test_send_trigger_silent_on_not_enough_rights():
    """TelegramBadRequest 'not enough rights to send' не должен попадать в logger.exception."""
    from app.bot.handlers import matching

    trigger = MagicMock(id=42)
    msg = _send_message()
    session = AsyncMock()

    saved_msg = MagicMock()
    saved_msg.dice = None
    saved_msg.send_copy = AsyncMock(
        side_effect=TelegramBadRequest(
            method=MagicMock(),
            message="Bad Request: not enough rights to send text messages to the chat",
        )
    )

    with (
        patch.object(matching.permissions, "is_missing", new=AsyncMock(return_value=False)),
        patch.object(matching.permissions, "record_missing", new=AsyncMock()) as mock_record,
        patch("app.bot.handlers.matching.Message") as mock_message_cls,
        patch("app.bot.handlers.matching.increment_usage", new_callable=AsyncMock),
        patch.object(matching.logger, "exception") as mock_exc,
    ):
        mock_message_cls.model_validate.return_value = saved_msg
        await matching._send_trigger_message(_send_message_content(), {}, msg, trigger, session)

    mock_exc.assert_not_called()
    mock_record.assert_awaited_once_with(-100, "can_send_messages")


async def test_send_trigger_silent_on_retry_after():
    """TelegramRetryAfter не должен попадать в logger.exception."""
    from app.bot.handlers import matching

    trigger = MagicMock(id=42)
    msg = _send_message()
    session = AsyncMock()

    saved_msg = MagicMock()
    saved_msg.dice = None
    saved_msg.send_copy = AsyncMock(
        side_effect=TelegramRetryAfter(
            method=MagicMock(),
            message="Flood control exceeded",
            retry_after=11,
        )
    )

    with (
        patch.object(matching.permissions, "is_missing", new=AsyncMock(return_value=False)),
        patch("app.bot.handlers.matching.Message") as mock_message_cls,
        patch("app.bot.handlers.matching.increment_usage", new_callable=AsyncMock),
        patch.object(matching.logger, "exception") as mock_exc,
    ):
        mock_message_cls.model_validate.return_value = saved_msg
        await matching._send_trigger_message(_send_message_content(), {}, msg, trigger, session)

    mock_exc.assert_not_called()


async def test_send_trigger_topic_closed_silent():
    from app.bot.handlers import matching

    trigger = MagicMock(id=42)
    msg = _send_message()
    session = AsyncMock()

    saved_msg = MagicMock()
    saved_msg.dice = None
    saved_msg.send_copy = AsyncMock(
        side_effect=TelegramBadRequest(method=MagicMock(), message="Bad Request: TOPIC_CLOSED")
    )

    with (
        patch.object(matching.permissions, "is_missing", new=AsyncMock(return_value=False)),
        patch("app.bot.handlers.matching.Message") as mock_message_cls,
        patch("app.bot.handlers.matching.increment_usage", new_callable=AsyncMock),
        patch.object(matching.logger, "exception") as mock_exc,
    ):
        mock_message_cls.model_validate.return_value = saved_msg
        await matching._send_trigger_message(_send_message_content(), {}, msg, trigger, session)

    mock_exc.assert_not_called()


async def test_send_trigger_unknown_bad_request_is_logged():
    """Неизвестный TelegramBadRequest должен попадать в logger.exception для расследования."""
    from app.bot.handlers import matching

    trigger = MagicMock(id=42)
    msg = _send_message()
    session = AsyncMock()

    saved_msg = MagicMock()
    saved_msg.dice = None
    saved_msg.send_copy = AsyncMock(
        side_effect=TelegramBadRequest(method=MagicMock(), message="Bad Request: MESSAGE_TOO_LONG")
    )

    with (
        patch.object(matching.permissions, "is_missing", new=AsyncMock(return_value=False)),
        patch("app.bot.handlers.matching.Message") as mock_message_cls,
        patch("app.bot.handlers.matching.increment_usage", new_callable=AsyncMock),
        patch.object(matching.logger, "exception") as mock_exc,
    ):
        mock_message_cls.model_validate.return_value = saved_msg
        await matching._send_trigger_message(_send_message_content(), {}, msg, trigger, session)

    mock_exc.assert_called_once()


async def test_send_trigger_forbidden_deactivates_chat():
    from app.bot.handlers import matching

    trigger = MagicMock(id=42)
    msg = _send_message()
    session = AsyncMock()
    db_chat = MagicMock(is_active=True)
    session.get = AsyncMock(return_value=db_chat)

    saved_msg = MagicMock()
    saved_msg.dice = None
    saved_msg.send_copy = AsyncMock(
        side_effect=TelegramForbiddenError(method=MagicMock(), message="Forbidden: bot was kicked")
    )

    with (
        patch.object(matching.permissions, "is_missing", new=AsyncMock(return_value=False)),
        patch("app.bot.handlers.matching.Message") as mock_message_cls,
        patch("app.bot.handlers.matching.increment_usage", new_callable=AsyncMock),
    ):
        mock_message_cls.model_validate.return_value = saved_msg
        await matching._send_trigger_message(_send_message_content(), {}, msg, trigger, session)

    assert db_chat.is_active is False
    session.commit.assert_awaited_once()
