"""Заблокированные создателем секции настроек в боте: callback'и админки и /welcome."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.bot.callback_data.admin import CaptchaTypeCallback, LanguageCallback, SettingsCallback
from app.bot.callback_data.moderation import ModerationSettingsCallback
from app.bot.handlers import admin as admin_handlers
from app.bot.handlers.chat_moderation import (
    on_duration_action,
    on_gban_toggle,
    on_limit_change,
    on_punishment_toggle,
)
from app.bot.handlers.welcome import welcome_command
from app.db.models.chat import Chat
from app.db.models.settings_audit import SettingsAuditLog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import create_chat

LOCKABLE = ["general", "captcha", "moderation", "triggers", "tags", "welcome", "autodelete", "other"]


def _make_i18n() -> MagicMock:
    i18n = MagicMock()
    i18n.error.no.rights.return_value = "No rights"
    i18n.error.section.locked.return_value = "Section locked"
    i18n.settings.updated.return_value = "Updated"
    i18n.btn.moderation.true.return_value = "on"
    i18n.btn.back.return_value = "back"
    i18n.mod.duration.btn.return_value = "duration"
    i18n.mod.punishment.btn.return_value = "punishment"
    i18n.mod.punishment.ban.return_value = "ban"
    i18n.mod.punishment.mute.return_value = "mute"
    i18n.moderation.gban.toggle.return_value = "gban"
    i18n.mod.settings.title.return_value = "Moderation"
    return i18n


def _make_callback(chat_id: int, status: str = "administrator", user_id: int = 555) -> MagicMock:
    callback = MagicMock()
    callback.from_user = MagicMock(id=user_id)
    callback.message = MagicMock()
    callback.message.chat = MagicMock(id=chat_id)
    callback.message.chat.get_member = AsyncMock(return_value=MagicMock(status=status))
    callback.message.edit_reply_markup = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    return callback


def _make_admin_calls(callback: MagicMock, session: AsyncSession, chat: Chat, i18n: MagicMock) -> dict:
    return {
        "toggle_captcha": lambda user=None: admin_handlers.toggle_captcha(
            callback, SettingsCallback(action="toggle_captcha"), session, i18n, chat, user=user
        ),
        "set_captcha_type": lambda user=None: admin_handlers.set_captcha_type(
            callback, CaptchaTypeCallback(type="webapp"), session, i18n, chat, user=user
        ),
        "set_captcha_timeout": lambda user=None: admin_handlers.set_captcha_timeout(
            callback, SettingsCallback(action="set_captcha_timeout", value="600"), session, i18n, chat, user=user
        ),
        "captcha_attempts_incr": lambda user=None: admin_handlers.captcha_attempts_incr(
            callback, session, i18n, chat, user=user
        ),
        "captcha_attempts_decr": lambda user=None: admin_handlers.captcha_attempts_decr(
            callback, session, i18n, chat, user=user
        ),
        "set_captcha_ban_duration": lambda user=None: admin_handlers.set_captcha_ban_duration(
            callback, SettingsCallback(action="set_captcha_ban_duration", value="600"), session, i18n, chat, user=user
        ),
        "toggle_admins_only": lambda user=None: admin_handlers.toggle_admins_only(
            callback, SettingsCallback(action="toggle_admins_only"), session, i18n, chat, user=user
        ),
        "toggle_triggers": lambda user=None: admin_handlers.toggle_triggers(
            callback, SettingsCallback(action="toggle_triggers"), session, i18n, chat, user=user
        ),
        "toggle_moderation": lambda user=None: admin_handlers.toggle_moderation(
            callback, SettingsCallback(action="toggle_moderation"), session, i18n, chat, user=user
        ),
        "toggle_tags": lambda user=None: admin_handlers.toggle_tags(callback, session, i18n, chat, user=user),
        "clear_confirm": lambda user=None: admin_handlers.clear_confirm(callback, session, i18n, chat, user=user),
        "set_timezone": lambda user=None: admin_handlers.set_timezone(
            callback, SettingsCallback(action="set_timezone", value="Europe/Moscow"), session, i18n, chat, user=user
        ),
        "on_language_select": lambda user=None: admin_handlers.on_language_select(
            callback, LanguageCallback(code="en"), session, i18n, chat, user=user
        ),
    }


def _snapshot(chat: Chat) -> tuple:
    return (
        chat.captcha_enabled,
        chat.captcha_type,
        chat.captcha_timeout,
        chat.captcha_max_attempts,
        chat.captcha_ban_duration,
        chat.admins_only_add,
        chat.module_triggers,
        chat.module_moderation,
        chat.tags_enabled,
        chat.timezone,
        chat.language_code,
    )


ADMIN_HANDLERS = [
    "toggle_captcha",
    "set_captcha_type",
    "set_captcha_timeout",
    "captcha_attempts_incr",
    "captcha_attempts_decr",
    "set_captcha_ban_duration",
    "toggle_admins_only",
    "toggle_triggers",
    "toggle_moderation",
    "toggle_tags",
    "clear_confirm",
    "set_timezone",
    "on_language_select",
]


@pytest.mark.parametrize("handler_name", ADMIN_HANDLERS)
async def test_admin_setter_refused_when_section_locked(db_session: AsyncSession, handler_name: str) -> None:
    chat = await create_chat(db_session, settings_locked_sections=LOCKABLE)
    await db_session.commit()
    i18n = _make_i18n()
    callback = _make_callback(chat.id)

    with patch.object(admin_handlers, "delete_all_triggers_by_chat", new_callable=AsyncMock) as delete_all:
        await _make_admin_calls(callback, db_session, chat, i18n)[handler_name]()

    callback.answer.assert_awaited_once_with("Section locked", show_alert=True)
    assert delete_all.await_count == 0
    await db_session.refresh(chat)
    assert _snapshot(chat) == (False, "emoji", 300, 3, 259200, False, True, True, False, "UTC", "ru")
    audit = await db_session.execute(select(SettingsAuditLog).where(SettingsAuditLog.chat_id == chat.id))
    assert audit.scalars().all() == []


async def test_creator_bypasses_section_lock(db_session: AsyncSession) -> None:
    chat = await create_chat(db_session, settings_locked_sections=LOCKABLE)
    await db_session.commit()
    i18n = _make_i18n()
    callback = _make_callback(chat.id, status="creator")

    with patch.object(admin_handlers, "get_captcha_settings_keyboard") as keyboard:
        keyboard.return_value.as_markup.return_value = MagicMock()
        await _make_admin_calls(callback, db_session, chat, i18n)["toggle_captcha"]()

    callback.answer.assert_awaited_once_with("Updated")
    await db_session.refresh(chat)
    assert chat.captcha_enabled is True


async def test_bot_moderator_bypasses_section_lock(db_session: AsyncSession) -> None:
    chat = await create_chat(db_session, settings_locked_sections=LOCKABLE)
    await db_session.commit()
    i18n = _make_i18n()
    callback = _make_callback(chat.id, status="administrator")
    user = MagicMock(id=987654, is_bot_moderator=True)

    with patch.object(admin_handlers, "get_captcha_settings_keyboard") as keyboard:
        keyboard.return_value.as_markup.return_value = MagicMock()
        await _make_admin_calls(callback, db_session, chat, i18n)["toggle_captcha"](user=user)

    callback.answer.assert_awaited_once_with("Updated")
    await db_session.refresh(chat)
    assert chat.captcha_enabled is True


MODERATION_ACTIONS = ["limit", "punishment", "gban", "duration"]


async def _invoke_moderation(
    action: str,
    callback: MagicMock,
    session: AsyncSession,
    chat: Chat,
    i18n: MagicMock,
    user: MagicMock | None = None,
) -> None:
    if action == "limit":
        data = ModerationSettingsCallback(action="limit", value="incr")
        await on_limit_change(callback, data, session, chat, i18n, user=user)
    elif action == "punishment":
        await on_punishment_toggle(callback, session, chat, i18n, user=user)
    elif action == "gban":
        data = ModerationSettingsCallback(action="gban", value="toggle")
        await on_gban_toggle(callback, data, session, chat, i18n, user=user)
    else:
        data = ModerationSettingsCallback(action="duration", value="600")
        await on_duration_action(callback, data, session, chat, i18n, user=user)


@pytest.mark.parametrize("action", MODERATION_ACTIONS)
async def test_moderation_setter_refused_when_section_locked(db_session: AsyncSession, action: str) -> None:
    chat = await create_chat(db_session, module_moderation=True, settings_locked_sections=["moderation", "other"])
    await db_session.commit()
    i18n = _make_i18n()
    callback = _make_callback(chat.id)

    await _invoke_moderation(action, callback, db_session, chat, i18n)

    callback.answer.assert_awaited_once_with("Section locked", show_alert=True)
    await db_session.refresh(chat)
    assert (chat.warn_limit, chat.warn_punishment, chat.gban_enabled, chat.warn_duration) == (3, "ban", False, 0)
    audit = await db_session.execute(select(SettingsAuditLog).where(SettingsAuditLog.chat_id == chat.id))
    assert audit.scalars().all() == []


async def test_moderation_creator_bypasses_section_lock(db_session: AsyncSession) -> None:
    chat = await create_chat(db_session, module_moderation=True, settings_locked_sections=["moderation"])
    await db_session.commit()
    i18n = _make_i18n()
    callback = _make_callback(chat.id, status="creator")

    await _invoke_moderation("limit", callback, db_session, chat, i18n)

    await db_session.refresh(chat)
    assert chat.warn_limit == 4


def _make_welcome_message(chat_id: int, reply_msg: MagicMock | None = None, user_id: int = 456) -> MagicMock:
    msg = MagicMock()
    msg.chat = MagicMock(id=chat_id, type="supergroup")
    msg.from_user = MagicMock(id=user_id)
    msg.answer = AsyncMock()
    msg.chat.get_member = AsyncMock(return_value=MagicMock(status="administrator"))
    msg.reply_to_message = reply_msg
    return msg


def _make_reply_message() -> MagicMock:
    reply = MagicMock()
    reply.html_text = "<b>Welcome!</b>"
    reply.model_dump.return_value = {"text": "Welcome!"}
    return reply


def _make_command(args: str | None) -> MagicMock:
    cmd = MagicMock()
    cmd.args = args
    return cmd


async def test_welcome_set_refused_when_section_locked(db_session: AsyncSession) -> None:
    chat = await create_chat(db_session, settings_locked_sections=["welcome"])
    await db_session.commit()
    i18n = _make_i18n()
    msg = _make_welcome_message(chat.id, reply_msg=_make_reply_message())

    await welcome_command(msg, _make_command("set"), db_session, i18n, chat)

    msg.answer.assert_awaited_once_with("Section locked", parse_mode="HTML")
    await db_session.refresh(chat)
    assert chat.welcome_enabled is False


async def test_welcome_delete_refused_when_section_locked(db_session: AsyncSession) -> None:
    chat = await create_chat(
        db_session,
        settings_locked_sections=["welcome"],
        welcome_enabled=True,
        welcome_message={"text": "Hello newcomer!"},
    )
    await db_session.commit()
    i18n = _make_i18n()
    msg = _make_welcome_message(chat.id)

    await welcome_command(msg, _make_command("delete"), db_session, i18n, chat)

    msg.answer.assert_awaited_once_with("Section locked", parse_mode="HTML")
    await db_session.refresh(chat)
    assert chat.welcome_enabled is True


async def test_welcome_set_writes_audit(db_session: AsyncSession) -> None:
    chat = await create_chat(db_session)
    await db_session.commit()
    i18n = _make_i18n()
    msg = _make_welcome_message(chat.id, reply_msg=_make_reply_message())

    await welcome_command(msg, _make_command("set"), db_session, i18n, chat)

    audit = await db_session.execute(select(SettingsAuditLog).where(SettingsAuditLog.chat_id == chat.id))
    entries = audit.scalars().all()
    assert len(entries) == 1
    assert entries[0].section == "welcome"
    assert entries[0].user_id == 456
    fields = {change["field"] for change in entries[0].changes}
    assert fields == {"welcome_enabled", "welcome_message"}


async def test_welcome_delete_writes_audit(db_session: AsyncSession) -> None:
    chat = await create_chat(db_session, welcome_enabled=True, welcome_message={"text": "Hello newcomer!"})
    await db_session.commit()
    i18n = _make_i18n()
    msg = _make_welcome_message(chat.id)

    await welcome_command(msg, _make_command("delete"), db_session, i18n, chat)

    audit = await db_session.execute(select(SettingsAuditLog).where(SettingsAuditLog.chat_id == chat.id))
    entries = audit.scalars().all()
    assert len(entries) == 1
    assert entries[0].section == "welcome"
    fields = {change["field"] for change in entries[0].changes}
    assert fields == {"welcome_enabled", "welcome_message"}
