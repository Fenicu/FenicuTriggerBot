"""Права администратора на callback-настройки модерации и аудит изменений."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from app.bot.callback_data.moderation import ModerationSettingsCallback
from app.bot.handlers.chat_moderation import (
    on_duration_action,
    on_gban_toggle,
    on_limit_change,
    on_punishment_toggle,
)
from app.db.models.chat import Chat
from app.db.models.settings_audit import SettingsAuditLog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import create_chat

ACTIONS = ["limit", "punishment", "gban", "duration"]


def _make_i18n() -> MagicMock:
    i18n = MagicMock()
    i18n.error.no.rights.return_value = "No rights"
    i18n.mod.duration.btn.return_value = "duration"
    i18n.mod.punishment.btn.return_value = "punishment"
    i18n.mod.punishment.ban.return_value = "ban"
    i18n.mod.punishment.mute.return_value = "mute"
    i18n.moderation.gban.toggle.return_value = "gban"
    i18n.btn.moderation.true.return_value = "on"
    i18n.btn.back.return_value = "back"
    return i18n


def _make_callback(chat_id: int, status: str = "member", user_id: int = 555) -> MagicMock:
    callback = MagicMock()
    callback.from_user = MagicMock(id=user_id)
    callback.message = MagicMock()
    callback.message.chat = MagicMock(id=chat_id)
    callback.message.chat.get_member = AsyncMock(return_value=MagicMock(status=status))
    callback.message.edit_reply_markup = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    return callback


async def _invoke(action: str, callback: MagicMock, session: AsyncSession, chat: Chat, i18n: MagicMock) -> None:
    if action == "limit":
        data = ModerationSettingsCallback(action="limit", value="incr")
        await on_limit_change(callback, data, session, chat, i18n)
    elif action == "punishment":
        await on_punishment_toggle(callback, session, chat, i18n)
    elif action == "gban":
        data = ModerationSettingsCallback(action="gban", value="toggle")
        await on_gban_toggle(callback, data, session, chat, i18n)
    else:
        data = ModerationSettingsCallback(action="duration", value="600")
        await on_duration_action(callback, data, session, chat, i18n)


def _snapshot(chat: Chat) -> tuple:
    return (chat.warn_limit, chat.warn_punishment, chat.gban_enabled, chat.warn_duration)


@pytest.mark.parametrize("action", ACTIONS)
async def test_non_admin_press_is_denied_and_changes_nothing(db_session: AsyncSession, action: str) -> None:
    chat = await create_chat(db_session, module_moderation=True)
    i18n = _make_i18n()
    callback = _make_callback(chat.id, status="member")

    await _invoke(action, callback, db_session, chat, i18n)

    callback.answer.assert_awaited_once_with(i18n.error.no.rights(), show_alert=True)
    await db_session.refresh(chat)
    assert _snapshot(chat) == (3, "ban", False, 0)
    audit = await db_session.execute(select(SettingsAuditLog).where(SettingsAuditLog.chat_id == chat.id))
    assert audit.scalars().all() == []


@pytest.mark.parametrize(
    ("action", "field", "expected"),
    [
        ("limit", "warn_limit", 4),
        ("punishment", "warn_punishment", "mute"),
        ("gban", "gban_enabled", True),
        ("duration", "warn_duration", 600),
    ],
)
async def test_admin_press_applies_and_writes_audit(
    db_session: AsyncSession, action: str, field: str, expected: object
) -> None:
    chat = await create_chat(db_session, module_moderation=True)
    i18n = _make_i18n()
    callback = _make_callback(chat.id, status="administrator")

    await _invoke(action, callback, db_session, chat, i18n)

    await db_session.refresh(chat)
    assert getattr(chat, field) == expected

    audit = await db_session.execute(select(SettingsAuditLog).where(SettingsAuditLog.chat_id == chat.id))
    entries = audit.scalars().all()
    assert len(entries) == 1
    assert entries[0].user_id == 555
    assert entries[0].changes == [{"field": field, "old": entries[0].changes[0]["old"], "new": expected}]
