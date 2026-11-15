"""Валидация значений callback-настроек перед сохранением."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.bot.callback_data.admin import LanguageCallback, SettingsCallback
from app.bot.callback_data.moderation import ModerationSettingsCallback
from app.bot.handlers import admin as admin_handlers
from app.bot.handlers.chat_moderation import on_duration_action
from app.db.models.chat import Chat
from app.db.models.settings_audit import SettingsAuditLog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import create_chat


def _make_i18n() -> MagicMock:
    i18n = MagicMock()
    i18n.error.no.rights.return_value = "No rights"
    i18n.error.section.locked.return_value = "Locked"
    i18n.error.invalid.timezone.return_value = "Invalid timezone"
    i18n.error.invalid.language.return_value = "Invalid language"
    i18n.error.invalid.duration.return_value = "Invalid duration"
    i18n.settings.updated.return_value = "Updated"
    i18n.mod.duration.btn.return_value = "duration"
    i18n.mod.punishment.btn.return_value = "punishment"
    return i18n


def _make_callback(chat_id: int) -> MagicMock:
    callback = MagicMock()
    callback.from_user = MagicMock(id=555)
    callback.message = MagicMock()
    callback.message.chat = MagicMock(id=chat_id)
    callback.message.chat.get_member = AsyncMock(return_value=MagicMock(status="administrator"))
    callback.message.edit_text = AsyncMock()
    callback.message.edit_reply_markup = AsyncMock()
    callback.answer = AsyncMock()
    return callback


async def _audit_entries(session: AsyncSession, chat: Chat) -> list[SettingsAuditLog]:
    result = await session.execute(select(SettingsAuditLog).where(SettingsAuditLog.chat_id == chat.id))
    return list(result.scalars().all())


async def test_invalid_timezone_is_rejected(db_session: AsyncSession) -> None:
    chat = await create_chat(db_session)
    await db_session.commit()
    i18n = _make_i18n()
    callback = _make_callback(chat.id)

    await admin_handlers.set_timezone(
        callback, SettingsCallback(action="set_timezone", value="Mars/Phobos"), db_session, i18n, chat
    )

    callback.answer.assert_awaited_once_with("Invalid timezone", show_alert=True)
    await db_session.refresh(chat)
    assert chat.timezone == "UTC"
    assert await _audit_entries(db_session, chat) == []


async def test_valid_timezone_is_applied(db_session: AsyncSession) -> None:
    chat = await create_chat(db_session)
    await db_session.commit()
    i18n = _make_i18n()
    callback = _make_callback(chat.id)

    with patch.object(admin_handlers, "_update_settings_message", new_callable=AsyncMock):
        await admin_handlers.set_timezone(
            callback, SettingsCallback(action="set_timezone", value="Europe/Moscow"), db_session, i18n, chat
        )

    await db_session.refresh(chat)
    assert chat.timezone == "Europe/Moscow"


async def test_unsupported_language_is_rejected(db_session: AsyncSession) -> None:
    chat = await create_chat(db_session)
    await db_session.commit()
    i18n = _make_i18n()
    callback = _make_callback(chat.id)

    await admin_handlers.on_language_select(callback, LanguageCallback(code="xx"), db_session, i18n, chat)

    callback.answer.assert_awaited_once_with("Invalid language", show_alert=True)
    await db_session.refresh(chat)
    assert chat.language_code == "ru"
    assert await _audit_entries(db_session, chat) == []


async def test_supported_language_is_applied(db_session: AsyncSession) -> None:
    chat = await create_chat(db_session)
    await db_session.commit()
    i18n = _make_i18n()
    callback = _make_callback(chat.id)
    new_i18n = MagicMock()
    new_i18n.lang.display.name.return_value = "English"

    with (
        patch.object(admin_handlers, "translator_hub") as hub,
        patch.object(admin_handlers, "valkey") as valkey,
    ):
        hub.get_translator_by_locale.return_value = new_i18n
        valkey.set = AsyncMock()
        await admin_handlers.on_language_select(callback, LanguageCallback(code="en"), db_session, i18n, chat)

    await db_session.refresh(chat)
    assert chat.language_code == "en"


@pytest.mark.parametrize("value", ["12345", "abc"])
async def test_unoffered_warn_duration_is_rejected(db_session: AsyncSession, value: str) -> None:
    chat = await create_chat(db_session, module_moderation=True)
    await db_session.commit()
    i18n = _make_i18n()
    callback = _make_callback(chat.id)

    await on_duration_action(
        callback, ModerationSettingsCallback(action="duration", value=value), db_session, chat, i18n
    )

    callback.answer.assert_awaited_once_with("Invalid duration", show_alert=True)
    await db_session.refresh(chat)
    assert chat.warn_duration == 0
    assert await _audit_entries(db_session, chat) == []
