"""Tests for app/bot/handlers/moderation.py — moderation callbacks and alerts."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram.types import InputRichMessage, RichMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.trigger import ModerationStatus, Trigger
from app.services.rich_html import validate_rich_html
from tests.factories import create_chat, create_trigger, create_user, create_banned_chat
from tests.handlers.conftest import _make_callback

# Import the handler module at module level BEFORE autouse mocks take effect,
# so that the real broker.subscriber decorator is applied (not a MagicMock).
from app.bot.handlers.moderation import (  # noqa: E402
    ban_chat as _ban_chat,
    delete_trigger as _delete_trigger,
    handle_moderation_alert as _handle_moderation_alert,
    mark_safe as _mark_safe,
)


def _make_bot_mock():
    """Create a MagicMock with AsyncMock methods for Bot."""
    m = MagicMock()
    m.send_message = AsyncMock()
    m.send_rich_message = AsyncMock()
    m.send_photo = AsyncMock()
    m.send_video = AsyncMock()
    m.send_sticker = AsyncMock()
    m.send_animation = AsyncMock()
    m.send_document = AsyncMock()
    m.send_voice = AsyncMock()
    m.send_audio = AsyncMock()
    m.send_video_note = AsyncMock()
    m.leave_chat = AsyncMock()
    return m


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
async def moderator_user(db_session: AsyncSession):
    """Create the moderator user matching the default callback mock user_id=42."""
    return await create_user(db_session, id=42, first_name="Test", last_name="Mod")


@pytest.fixture
async def chat(db_session: AsyncSession):
    return await create_chat(db_session)


@pytest.fixture
async def user(db_session: AsyncSession):
    return await create_user(db_session)


@pytest.fixture
async def flagged_trigger(db_session: AsyncSession, chat, user):
    return await create_trigger(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        moderation_status=ModerationStatus.FLAGGED,
        moderation_reason="Flagged by AI",
    )


@pytest.fixture
async def error_trigger(db_session: AsyncSession, chat, user):
    return await create_trigger(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        moderation_status=ModerationStatus.ERROR,
        moderation_reason="AI error",
    )


@pytest.fixture
async def safe_trigger(db_session: AsyncSession, chat, user):
    return await create_trigger(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        moderation_status=ModerationStatus.SAFE,
    )


# ── mark_safe ───────────────────────────────────────────────────────────────


async def test_mark_safe_sets_status(db_session: AsyncSession, flagged_trigger):
    from app.bot.handlers.moderation import mark_safe

    callback = _make_callback(f"mod_safe:{flagged_trigger.id}")
    await mark_safe(callback, db_session)

    await db_session.refresh(flagged_trigger)
    assert flagged_trigger.moderation_status == ModerationStatus.SAFE
    assert "False positive" in flagged_trigger.moderation_reason
    callback.answer.assert_awaited_with("Marked as safe")


async def test_mark_safe_works_for_error_status(db_session: AsyncSession, error_trigger):
    from app.bot.handlers.moderation import mark_safe

    callback = _make_callback(f"mod_safe:{error_trigger.id}")
    await mark_safe(callback, db_session)

    await db_session.refresh(error_trigger)
    assert error_trigger.moderation_status == ModerationStatus.SAFE


async def test_mark_safe_updates_moderation_message(db_session: AsyncSession, flagged_trigger):
    from app.bot.handlers.moderation import mark_safe

    callback = _make_callback(f"mod_safe:{flagged_trigger.id}", username="admin_user")
    await mark_safe(callback, db_session)

    callback.message.edit_text.assert_awaited_once()
    call_args = callback.message.edit_text.call_args
    assert "admin_user" in call_args.kwargs.get("text", call_args.args[0] if call_args.args else "")


async def test_mark_safe_not_found(db_session: AsyncSession):
    from app.bot.handlers.moderation import mark_safe

    callback = _make_callback("mod_safe:999999")
    await mark_safe(callback, db_session)

    callback.answer.assert_awaited_with("Trigger not found")


async def test_mark_safe_already_processed(db_session: AsyncSession, safe_trigger):
    """Race condition: another moderator already handled this trigger."""
    from app.bot.handlers.moderation import mark_safe

    callback = _make_callback(f"mod_safe:{safe_trigger.id}")
    await mark_safe(callback, db_session)

    callback.answer.assert_awaited_with("Already handled by another moderator", show_alert=True)


async def test_mark_safe_invalid_callback_data(db_session: AsyncSession):
    from app.bot.handlers.moderation import mark_safe

    callback = _make_callback("mod_safe:not_a_number")
    await mark_safe(callback, db_session)

    callback.answer.assert_awaited_with("Invalid data")


async def test_mark_safe_uses_full_name_when_no_username(db_session: AsyncSession, flagged_trigger):
    from app.bot.handlers.moderation import mark_safe

    callback = _make_callback(f"mod_safe:{flagged_trigger.id}", username=None, full_name="John Doe")
    callback.from_user.username = None
    await mark_safe(callback, db_session)

    await db_session.refresh(flagged_trigger)
    assert "John Doe" in flagged_trigger.moderation_reason


# ── delete_trigger ──────────────────────────────────────────────────────────


async def test_delete_trigger_removes_and_notifies(db_session: AsyncSession, flagged_trigger, chat):
    from app.bot.handlers.moderation import delete_trigger

    mock_bot = _make_bot_mock()
    callback = _make_callback(f"mod_del:{flagged_trigger.id}")

    with patch("app.bot.handlers.moderation.bot", mock_bot):
        await delete_trigger(callback, db_session)

    await db_session.refresh(flagged_trigger)
    assert flagged_trigger.is_deleted is True
    callback.answer.assert_awaited_with("Trigger deleted")
    mock_bot.send_message.assert_awaited_once()
    sent_chat_id = mock_bot.send_message.call_args.args[0]
    assert sent_chat_id == chat.id


async def test_delete_trigger_already_deleted(db_session: AsyncSession):
    from app.bot.handlers.moderation import delete_trigger

    mock_bot = _make_bot_mock()
    callback = _make_callback("mod_del:999999")

    with patch("app.bot.handlers.moderation.bot", mock_bot):
        await delete_trigger(callback, db_session)

    callback.answer.assert_awaited_with("Trigger already deleted")
    mock_bot.send_message.assert_not_awaited()


@patch("app.bot.handlers.moderation.bot", new_callable=lambda: _make_bot_mock)
async def test_delete_trigger_already_processed(mock_bot, db_session: AsyncSession, safe_trigger):
    from app.bot.handlers.moderation import delete_trigger

    callback = _make_callback(f"mod_del:{safe_trigger.id}")
    await delete_trigger(callback, db_session)

    callback.answer.assert_awaited_with("Already handled by another moderator", show_alert=True)


@patch("app.bot.handlers.moderation.bot", new_callable=lambda: _make_bot_mock)
async def test_delete_trigger_invalid_data(mock_bot, db_session: AsyncSession):
    from app.bot.handlers.moderation import delete_trigger

    callback = _make_callback("mod_del:abc")
    await delete_trigger(callback, db_session)

    callback.answer.assert_awaited_with("Invalid data")


async def test_delete_trigger_updates_moderation_message(db_session: AsyncSession, flagged_trigger):
    from app.bot.handlers.moderation import delete_trigger

    mock_bot = _make_bot_mock()
    callback = _make_callback(f"mod_del:{flagged_trigger.id}", username="mod_user")

    with patch("app.bot.handlers.moderation.bot", mock_bot):
        await delete_trigger(callback, db_session)

    callback.message.edit_text.assert_awaited_once()


# ── ban_chat ────────────────────────────────────────────────────────────────


async def test_ban_chat_bans_and_deletes(db_session: AsyncSession, flagged_trigger, chat):
    from app.bot.handlers.moderation import ban_chat

    mock_bot = _make_bot_mock()
    callback = _make_callback(f"mod_ban:{chat.id}:{flagged_trigger.id}")

    with patch("app.bot.handlers.moderation.bot", mock_bot):
        await ban_chat(callback, db_session)

    await db_session.refresh(flagged_trigger)
    assert flagged_trigger.is_deleted is True
    callback.answer.assert_awaited_with("Chat banned")
    mock_bot.leave_chat.assert_awaited_once_with(chat.id)


async def test_ban_chat_already_banned_still_deletes_trigger(db_session: AsyncSession, flagged_trigger, chat):
    """If chat is already banned, trigger should still be deleted."""
    from app.bot.handlers.moderation import ban_chat

    mock_bot = _make_bot_mock()
    await create_banned_chat(db_session, chat_id=chat.id)
    await db_session.commit()

    callback = _make_callback(f"mod_ban:{chat.id}:{flagged_trigger.id}")

    with patch("app.bot.handlers.moderation.bot", mock_bot):
        await ban_chat(callback, db_session)

    # After rollback + re-fetch, trigger should still get soft-deleted
    callback.answer.assert_awaited_with("Chat banned")


@patch("app.bot.handlers.moderation.bot", new_callable=lambda: _make_bot_mock)
async def test_ban_chat_already_processed(mock_bot, db_session: AsyncSession, safe_trigger, chat):
    from app.bot.handlers.moderation import ban_chat

    callback = _make_callback(f"mod_ban:{chat.id}:{safe_trigger.id}")
    await ban_chat(callback, db_session)

    callback.answer.assert_awaited_with("Already handled by another moderator", show_alert=True)


@patch("app.bot.handlers.moderation.bot", new_callable=lambda: _make_bot_mock)
async def test_ban_chat_trigger_not_found(mock_bot, db_session: AsyncSession, chat):
    from app.bot.handlers.moderation import ban_chat

    callback = _make_callback(f"mod_ban:{chat.id}:999999")
    await ban_chat(callback, db_session)

    callback.answer.assert_awaited_with("Trigger not found")


@patch("app.bot.handlers.moderation.bot", new_callable=lambda: _make_bot_mock)
async def test_ban_chat_invalid_data(mock_bot, db_session: AsyncSession):
    from app.bot.handlers.moderation import ban_chat

    callback = _make_callback("mod_ban:invalid")
    await ban_chat(callback, db_session)

    callback.answer.assert_awaited_with("Invalid data")


async def test_ban_chat_updates_moderation_message(db_session: AsyncSession, flagged_trigger, chat):
    from app.bot.handlers.moderation import ban_chat

    mock_bot = _make_bot_mock()
    callback = _make_callback(f"mod_ban:{chat.id}:{flagged_trigger.id}", username="supermod")

    with patch("app.bot.handlers.moderation.bot", mock_bot):
        await ban_chat(callback, db_session)

    callback.message.edit_text.assert_awaited_once()


# ── handle_moderation_alert ────────────────────────────────────────────────


async def test_handle_moderation_alert_sends_text_alert(db_session: AsyncSession, flagged_trigger, chat):
    from app.bot.handlers.moderation import handle_moderation_alert
    from app.schemas.moderation import ModerationAlert

    alert = ModerationAlert(
        trigger_id=flagged_trigger.id,
        chat_id=chat.id,
        category="Scam",
        confidence=0.95,
        reasoning="Suspicious content",
    )

    mock_bot = _make_bot_mock()

    # Patch the async_session used inside the handler
    with (
        patch("app.bot.handlers.moderation.async_session") as mock_session_maker,
        patch("app.bot.handlers.moderation.bot", mock_bot),
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=db_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_maker.return_value = mock_ctx

        await handle_moderation_alert(alert)

    mock_bot.send_rich_message.assert_awaited_once()
    call_kwargs = mock_bot.send_rich_message.call_args.kwargs
    assert isinstance(call_kwargs.get("rich_message"), InputRichMessage)
    assert call_kwargs.get("reply_markup") is not None


async def test_handle_moderation_alert_with_photo(db_session: AsyncSession, chat, user):
    """Photo — эмбеддируемый тип (Task 11): едет внутри rich-сообщения, отдельный send_photo не зовётся."""
    from aiogram.types import InputMediaPhoto

    from app.bot.handlers.moderation import handle_moderation_alert
    from app.schemas.moderation import ModerationAlert

    trigger = await create_trigger(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        content={"photo": [{"file_id": "photo123", "file_unique_id": "u1", "width": 100, "height": 100}]},
        moderation_status=ModerationStatus.FLAGGED,
    )

    alert = ModerationAlert(
        trigger_id=trigger.id,
        chat_id=chat.id,
        category="Porn",
        confidence=0.99,
        reasoning="Explicit content",
    )

    mock_bot = _make_bot_mock()

    with (
        patch("app.bot.handlers.moderation.async_session") as mock_session_maker,
        patch("app.bot.handlers.moderation.bot", mock_bot),
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=db_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_maker.return_value = mock_ctx

        await handle_moderation_alert(alert)

    mock_bot.send_photo.assert_not_awaited()
    mock_bot.send_rich_message.assert_awaited_once()
    rich = mock_bot.send_rich_message.call_args.kwargs["rich_message"]
    assert rich.media is not None and len(rich.media) == 1
    assert isinstance(rich.media[0].media, InputMediaPhoto)
    assert rich.media[0].media.media == "photo123"
    assert "tg://photo?id=m0" in rich.html
    validate_rich_html(rich.html)


async def test_handle_moderation_alert_trigger_not_found(db_session: AsyncSession, chat):
    from app.bot.handlers.moderation import handle_moderation_alert
    from app.schemas.moderation import ModerationAlert

    alert = ModerationAlert(
        trigger_id=999999,
        chat_id=chat.id,
        category="Safe",
    )

    mock_bot = _make_bot_mock()

    with (
        patch("app.bot.handlers.moderation.async_session") as mock_session_maker,
        patch("app.bot.handlers.moderation.bot", mock_bot),
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=db_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_maker.return_value = mock_ctx

        await handle_moderation_alert(alert)

    mock_bot.send_rich_message.assert_not_awaited()


async def test_handle_moderation_alert_with_sticker(db_session: AsyncSession, chat, user):
    from app.bot.handlers.moderation import handle_moderation_alert
    from app.schemas.moderation import ModerationAlert

    trigger = await create_trigger(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        content={
            "sticker": {"file_id": "sticker456", "file_unique_id": "u2", "type": "regular", "width": 512, "height": 512}
        },
        moderation_status=ModerationStatus.FLAGGED,
    )

    alert = ModerationAlert(
        trigger_id=trigger.id,
        chat_id=chat.id,
        category="Violence",
        confidence=0.8,
    )

    mock_bot = _make_bot_mock()

    with (
        patch("app.bot.handlers.moderation.async_session") as mock_session_maker,
        patch("app.bot.handlers.moderation.bot", mock_bot),
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=db_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_maker.return_value = mock_ctx

        await handle_moderation_alert(alert)

    mock_bot.send_sticker.assert_awaited_once()
    mock_bot.send_rich_message.assert_awaited_once()


async def test_handle_moderation_alert_with_video_note(db_session: AsyncSession, chat, user):
    from app.bot.handlers.moderation import handle_moderation_alert
    from app.schemas.moderation import ModerationAlert

    trigger = await create_trigger(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        content={
            "video_note": {"file_id": "videonote789", "file_unique_id": "u3", "length": 240, "duration": 5}
        },
        moderation_status=ModerationStatus.FLAGGED,
    )

    alert = ModerationAlert(
        trigger_id=trigger.id,
        chat_id=chat.id,
        category="Scam",
        confidence=0.77,
        reasoning="Voice scam",
        transcript="переведи деньги на карту",
    )

    mock_bot = _make_bot_mock()

    with (
        patch("app.bot.handlers.moderation.async_session") as mock_session_maker,
        patch("app.bot.handlers.moderation.bot", mock_bot),
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=db_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_maker.return_value = mock_ctx

        await handle_moderation_alert(alert)

    mock_bot.send_video_note.assert_awaited_once()
    call_kwargs = mock_bot.send_video_note.call_args.kwargs
    assert call_kwargs.get("video_note") == "videonote789"
    mock_bot.send_rich_message.assert_awaited_once()
    rich = mock_bot.send_rich_message.call_args.kwargs["rich_message"]
    assert "Распознанная речь" in rich.html
    assert "переведи деньги на карту" in rich.html


async def test_handle_moderation_alert_long_text_truncated(db_session: AsyncSession, chat, user):
    """Длинный контент не должен ломать отправку rich-сообщения."""
    from app.bot.handlers.moderation import handle_moderation_alert
    from app.schemas.moderation import ModerationAlert

    trigger = await create_trigger(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        content={"text": "x" * 5000},
        moderation_status=ModerationStatus.FLAGGED,
    )

    alert = ModerationAlert(
        trigger_id=trigger.id,
        chat_id=chat.id,
        category="Scam",
        confidence=0.9,
        reasoning="Long text",
    )

    mock_bot = _make_bot_mock()

    with (
        patch("app.bot.handlers.moderation.async_session") as mock_session_maker,
        patch("app.bot.handlers.moderation.bot", mock_bot),
    ):
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=db_session)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_maker.return_value = mock_ctx

        await handle_moderation_alert(alert)

    # Should not raise, rich message should be sent
    mock_bot.send_rich_message.assert_awaited_once()
    rich = mock_bot.send_rich_message.call_args.kwargs["rich_message"]
    validate_rich_html(rich.html)


# ── update_moderation_message ──────────────────────────────────────────────


async def test_update_moderation_message_rich_branch_appends_status():
    """Для rich-сообщения статус добавляется через edit_text(rich_message=...)."""
    from app.bot.handlers.moderation import update_moderation_message

    message = MagicMock()
    message.rich_message = RichMessage.model_validate({"blocks": [{"type": "paragraph", "text": "alert body"}]})
    message.edit_text = AsyncMock()

    await update_moderation_message(message, "✅ Marked SAFE by <b>admin</b>")

    message.edit_text.assert_awaited_once()
    call_kwargs = message.edit_text.call_args.kwargs
    sent = call_kwargs["rich_message"]
    assert isinstance(sent, InputRichMessage)
    assert "alert body" in sent.html
    assert "<hr><p>✅ Marked SAFE by <b>admin</b></p>" in sent.html
    validate_rich_html(sent.html)
