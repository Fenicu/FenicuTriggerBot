"""Устойчивость callback-настроек: недоступное сообщение и flood-control на edit."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import Chat as TgChat
from aiogram.types import InaccessibleMessage
from app.bot.callback_data.admin import SettingsCallback
from app.bot.callback_data.moderation import ModerationSettingsCallback
from app.bot.handlers import admin as admin_handlers
from app.bot.handlers.chat_moderation import on_limit_change
from app.db.models.chat import Chat
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import create_chat


def _make_i18n() -> MagicMock:
    i18n = MagicMock()
    i18n.error.callback.expired.return_value = "Message expired"
    i18n.error.no.rights.return_value = "No rights"
    i18n.error.section.locked.return_value = "Locked"
    i18n.settings.updated.return_value = "Updated"
    i18n.mod.duration.btn.return_value = "duration"
    i18n.mod.punishment.btn.return_value = "punishment"
    return i18n


def _make_callback(chat_id: int, message: object | None = None) -> MagicMock:
    callback = MagicMock()
    callback.from_user = MagicMock(id=555)
    if message is None:
        callback.message = MagicMock()
        callback.message.chat = MagicMock(id=chat_id)
        callback.message.chat.get_member = AsyncMock(return_value=MagicMock(status="administrator"))
        callback.message.edit_text = AsyncMock()
        callback.message.edit_reply_markup = AsyncMock()
    else:
        callback.message = message
    callback.answer = AsyncMock()
    return callback


def _inaccessible(chat_id: int) -> InaccessibleMessage:
    return InaccessibleMessage(chat=TgChat(id=chat_id, type="supergroup"), message_id=10, date=0)


async def _invoke_admin(callback: MagicMock, session: AsyncSession, chat: Chat, i18n: MagicMock) -> None:
    await admin_handlers.toggle_captcha(
        callback, SettingsCallback(action="toggle_captcha"), session, i18n, chat
    )


async def _invoke_moderation(callback: MagicMock, session: AsyncSession, chat: Chat, i18n: MagicMock) -> None:
    data = ModerationSettingsCallback(action="limit", value="incr")
    await on_limit_change(callback, data, session, chat, i18n)


INVOKERS = [_invoke_admin, _invoke_moderation]


@pytest.mark.parametrize("invoke", INVOKERS)
async def test_inaccessible_message_answers_alert(
    db_session: AsyncSession, invoke,  # noqa: ANN001
) -> None:
    chat = await create_chat(db_session)
    await db_session.commit()
    i18n = _make_i18n()
    callback = _make_callback(chat.id, message=_inaccessible(chat.id))

    await invoke(callback, db_session, chat, i18n)

    callback.answer.assert_awaited_once_with("Message expired", show_alert=True)


@pytest.mark.parametrize("invoke", INVOKERS)
async def test_retry_after_on_edit_is_swallowed(
    db_session: AsyncSession, invoke,  # noqa: ANN001
) -> None:
    chat = await create_chat(db_session)
    await db_session.commit()
    i18n = _make_i18n()
    callback = _make_callback(chat.id)
    error = TelegramRetryAfter(method=MagicMock(), message="Too Many Requests", retry_after=3)
    callback.message.edit_text = AsyncMock(side_effect=error)
    callback.message.edit_reply_markup = AsyncMock(side_effect=error)

    with (
        patch("app.bot.handlers.admin.get_captcha_settings_keyboard") as captcha_keyboard,
        patch("app.bot.handlers.chat_moderation.get_moderation_settings_keyboard") as moderation_keyboard,
    ):
        captcha_keyboard.return_value.as_markup.return_value = MagicMock()
        moderation_keyboard.return_value.as_markup.return_value = MagicMock()
        await invoke(callback, db_session, chat, i18n)

    callback.answer.assert_awaited_once_with()
