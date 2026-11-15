"""Навигация по списку триггеров: flood-retry и устаревшие (недоступные) сообщения."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import Chat, InaccessibleMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callback_data.triggers import TriggerEditCallback, TriggersListCallback
from tests.factories import create_chat, create_trigger
from tests.handlers.conftest import _make_callback


def _make_i18n() -> MagicMock:
    i18n = MagicMock()
    i18n.trigger.list.header.return_value = "Triggers"
    i18n.trigger.list.page.return_value = "Page 1/1"
    i18n.trigger.list.empty.return_value = "No triggers"
    i18n.trigger.list.outdated.return_value = "Message is too old"
    return i18n


@pytest.fixture
async def chat(db_session: AsyncSession):
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="listed")
    await db_session.commit()
    return chat


async def test_list_retries_after_flood_control(db_session, chat):
    from app.bot.handlers import management

    callback = _make_callback("x", chat_id=chat.id)
    callback.message.edit_text = AsyncMock(
        side_effect=[TelegramRetryAfter(method=MagicMock(), message="Flood", retry_after=3), None]
    )

    with patch.object(management.asyncio, "sleep", new_callable=AsyncMock) as mock_sleep:
        await management.on_triggers_list(callback, TriggersListCallback(page=1), db_session, _make_i18n())

    mock_sleep.assert_awaited_once_with(3)
    assert callback.message.edit_text.await_count == 2
    callback.answer.assert_awaited_once()


async def test_list_ignores_message_not_modified(db_session, chat):
    from app.bot.handlers import management

    callback = _make_callback("x", chat_id=chat.id)
    callback.message.edit_text = AsyncMock(
        side_effect=TelegramBadRequest(method=MagicMock(), message="Bad Request: message is not modified")
    )

    await management.on_triggers_list(callback, TriggersListCallback(page=1), db_session, _make_i18n())

    callback.answer.assert_awaited_once()


def _inaccessible_callback(chat_id: int) -> MagicMock:
    callback = _make_callback("x", chat_id=chat_id)
    callback.message = InaccessibleMessage(chat=Chat(id=chat_id, type="supergroup"), message_id=10, date=0)
    return callback


async def test_list_on_inaccessible_message_answers_with_alert(db_session, chat):
    """Callback от сообщения старше 48 часов: редактировать нечего, пользователь получает alert."""
    from app.bot.handlers import management

    callback = _inaccessible_callback(chat.id)

    await management.on_triggers_list(callback, TriggersListCallback(page=1), db_session, _make_i18n())

    callback.answer.assert_awaited_once_with("Message is too old", show_alert=True)


async def test_edit_on_inaccessible_message_answers_with_alert(db_session, chat):
    from app.bot.handlers import management

    callback = _inaccessible_callback(chat.id)
    bot = MagicMock()
    bot.get_chat_member = AsyncMock()

    await management.on_trigger_edit(callback, TriggerEditCallback(id=1, action="open"), db_session, bot, _make_i18n())

    callback.answer.assert_awaited_once_with("Message is too old", show_alert=True)
    bot.get_chat_member.assert_not_awaited()


async def test_list_callback_without_message_answers_with_alert(db_session):
    from app.bot.handlers import management

    callback = _make_callback("x")
    callback.message = None

    await management.on_triggers_list(callback, TriggersListCallback(page=1), db_session, _make_i18n())

    callback.answer.assert_awaited_once_with("Message is too old", show_alert=True)


def test_outdated_key_exists_in_all_locales():
    from pathlib import Path

    for locale in ("ru", "en"):
        text = Path(f"locales/{locale}/messages.ftl").read_text(encoding="utf-8")
        assert "\ntrigger-list-outdated = " in text, locale


