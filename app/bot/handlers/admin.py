from contextlib import suppress
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from fluentogram import TranslatorRunner
from sqlalchemy.ext.asyncio import AsyncSession
from yarl import URL

from app.bot.callback_data.admin import CaptchaTypeCallback, LanguageCallback, SettingsCallback
from app.bot.instance import bot
from app.bot.keyboards.admin import (
    get_captcha_ban_duration_keyboard,
    get_captcha_settings_keyboard,
    get_captcha_timeout_keyboard,
    get_clear_confirm_keyboard,
    get_language_keyboard,
    get_settings_keyboard,
    get_triggers_settings_keyboard,
)
from app.bot.keyboards.moderation import format_duration, get_moderation_settings_keyboard
from app.core.config import settings
from app.core.i18n import translator_hub
from app.core.valkey import valkey
from app.db.models.captcha_session import ChatCaptchaSession
from app.db.models.chat import Chat
from app.db.models.user import User
from app.services.audit_service import get_audit_log, record_settings_changes
from app.services.chat_service import (
    update_chat_settings,
    update_language,
)
from app.services.trigger_service import (
    delete_all_triggers_by_chat,
    delete_trigger_by_key,
    get_trigger_by_key,
)


class SettingsStates(StatesGroup):
    waiting_for_timezone = State()


router = Router()


async def _get_settings_text(chat: Chat, i18n: TranslatorRunner) -> str:
    """Получить текст настроек (главное меню — сводка)."""
    captcha_status = "✅" if chat.captcha_enabled else "❌"
    moderation_status = "✅" if chat.module_moderation else "❌"
    triggers_status = "✅" if chat.module_triggers else "❌"
    tags_status = "✅" if chat.tags_enabled else "❌"
    trusted_status = i18n.settings.trusted() if chat.is_trusted else ""

    captcha_detail = captcha_status
    if chat.captcha_enabled:
        captcha_type = i18n.settings.captcha.type
        type_name = captcha_type.emoji() if chat.captcha_type == "emoji" else captcha_type.webapp()
        timeout_text = format_duration(chat.captcha_timeout, i18n)
        captcha_detail = f"✅ | {type_name} | {timeout_text}"

    moderation_detail = moderation_status
    if chat.module_moderation:
        punishment = i18n.mod.punishment.ban() if chat.warn_punishment == "ban" else i18n.mod.punishment.mute()
        moderation_detail = f"✅ | {i18n.mod.settings.limit(limit=chat.warn_limit)} | {punishment}"

    text = (
        f"{i18n.settings.title()}\n\n"
        f"{i18n.settings.summary.captcha(status=captcha_detail)}\n"
        f"{i18n.settings.summary.moderation(status=moderation_detail)}\n"
        f"{i18n.settings.summary.triggers(status=triggers_status)}\n"
        f"{i18n.settings.summary.tags(status=tags_status)}\n"
        f"{i18n.settings.timezone(timezone=chat.timezone)}\n"
    )
    if trusted_status:
        text += f"\n{trusted_status}\n"
    return text


async def _update_settings_message(callback: CallbackQuery, chat: Chat, i18n: TranslatorRunner) -> None:
    """Обновить сообщение — вернуться в главное меню настроек."""
    text = await _get_settings_text(chat, i18n)
    bot_user = await callback.bot.me()
    await callback.message.edit_text(
        text,
        reply_markup=get_settings_keyboard(chat, i18n, bot_user.username),
        parse_mode="HTML",
    )


@router.message(Command("admin"))
async def admin_command(message: Message, i18n: TranslatorRunner, user: User) -> None:
    """Открыть админ-панель."""
    if message.from_user.id not in settings.BOT_ADMINS and not user.is_bot_moderator:
        await message.answer(i18n.error.no.rights(), parse_mode="HTML")
        return

    if message.chat.type != ChatType.PRIVATE:
        await message.answer(i18n.error.private.only(), parse_mode="HTML")
        return

    url = URL(settings.WEBAPP_URL)
    if settings.URL_PREFIX:
        url = url / settings.URL_PREFIX.strip("/")
    url = url / "webapp"
    if not url.path.endswith("/"):
        url = url.with_path(url.path + "/")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Open Admin Panel",
                    web_app=WebAppInfo(url=str(url)),
                )
            ]
        ]
    )
    await message.answer("Admin Panel", reply_markup=keyboard)


@router.message(Command("del"))
async def del_trigger(message: Message, command: CommandObject, session: AsyncSession, i18n: TranslatorRunner) -> None:
    """Удаление триггера по ключу."""
    if not command.args:
        with suppress(TelegramBadRequest):
            await message.answer(i18n.delete.usage(), parse_mode="HTML")
        return

    key_phrase = command.args

    trigger = await get_trigger_by_key(session, message.chat.id, key_phrase)
    if not trigger:
        with suppress(TelegramBadRequest):
            await message.answer(i18n.trigger.missing(), parse_mode="HTML")
        return

    user_member = await message.chat.get_member(message.from_user.id)
    is_admin = user_member.status in ("administrator", "creator")
    is_creator = trigger.created_by == message.from_user.id

    if not (is_admin or is_creator):
        with suppress(TelegramBadRequest):
            await message.answer(i18n.error.no.rights(), parse_mode="HTML")
        return

    deleted = await delete_trigger_by_key(session, message.chat.id, key_phrase)
    if deleted:
        with suppress(TelegramBadRequest):
            await message.answer(i18n.trigger.deleted(), parse_mode="HTML")
    else:
        with suppress(TelegramBadRequest):
            await message.answer(i18n.trigger.delete.error(), parse_mode="HTML")


@router.message(Command("settings"))
async def settings_command(message: Message, session: AsyncSession, i18n: TranslatorRunner, db_chat: Chat) -> None:
    """Показать настройки чата (главное меню)."""
    user_member = await message.chat.get_member(message.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await message.answer(i18n.error.no.rights(), parse_mode="HTML")
        return

    text = await _get_settings_text(db_chat, i18n)
    bot_user = await message.bot.me()
    await message.answer(
        text,
        reply_markup=get_settings_keyboard(db_chat, i18n, bot_user.username),
        parse_mode="HTML",
    )


@router.callback_query(SettingsCallback.filter(F.action == "settings_back"))
async def settings_back(callback: CallbackQuery, session: AsyncSession, i18n: TranslatorRunner, db_chat: Chat) -> None:
    """Возврат в главное меню настроек."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    await _update_settings_message(callback, db_chat, i18n)
    await callback.answer()


@router.callback_query(SettingsCallback.filter(F.action == "close"))
async def close_settings(callback: CallbackQuery) -> None:
    """Закрыть меню настроек."""
    await callback.message.delete()
    await callback.answer()


def _get_captcha_menu_text(chat: Chat, i18n: TranslatorRunner) -> str:
    """Получить текст подменю капчи."""
    captcha_status = "✅" if chat.captcha_enabled else "❌"
    captcha_type = i18n.settings.captcha.type
    type_name = captcha_type.emoji() if chat.captcha_type == "emoji" else captcha_type.webapp()
    timeout_text = format_duration(chat.captcha_timeout, i18n)
    ban_text = format_duration(chat.captcha_ban_duration, i18n)

    return (
        f"{i18n.settings.captcha.title()}\n\n"
        f"{i18n.settings.captcha.status(status=captcha_status)}\n"
        f"{i18n.settings.captcha.type.label(type=type_name)}\n"
        f"{i18n.settings.captcha.timeout.label(timeout=timeout_text)}\n"
        f"{i18n.settings.captcha.attempts.label(count=chat.captcha_max_attempts)}\n"
        f"{i18n.settings.captcha.ban.label(duration=ban_text)}\n"
    )


@router.callback_query(SettingsCallback.filter(F.action == "captcha_menu"))
async def captcha_menu(callback: CallbackQuery, i18n: TranslatorRunner, db_chat: Chat) -> None:
    """Показать подменю настроек капчи."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    await callback.message.edit_text(
        _get_captcha_menu_text(db_chat, i18n),
        reply_markup=get_captcha_settings_keyboard(db_chat, i18n),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(SettingsCallback.filter(F.action == "toggle_captcha"))
async def toggle_captcha(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    session: AsyncSession,
    i18n: TranslatorRunner,
    db_chat: Chat,
) -> None:
    """Переключить режим капчи."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    new_value = not db_chat.captcha_enabled
    await record_settings_changes(session, db_chat, callback.from_user.id, {"captcha_enabled": new_value})
    chat = await update_chat_settings(session, db_chat.id, captcha_enabled=new_value)

    await callback.message.edit_text(
        _get_captcha_menu_text(chat, i18n),
        reply_markup=get_captcha_settings_keyboard(chat, i18n),
        parse_mode="HTML",
    )
    await callback.answer(i18n.settings.updated())


@router.callback_query(CaptchaTypeCallback.filter())
async def set_captcha_type(
    callback: CallbackQuery,
    callback_data: CaptchaTypeCallback,
    session: AsyncSession,
    i18n: TranslatorRunner,
    db_chat: Chat,
) -> None:
    """Установить тип капчи."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    if db_chat.captcha_type == callback_data.type:
        await callback.answer()
        return

    await record_settings_changes(session, db_chat, callback.from_user.id, {"captcha_type": callback_data.type})
    chat = await update_chat_settings(session, db_chat.id, captcha_type=callback_data.type)

    await callback.message.edit_text(
        _get_captcha_menu_text(chat, i18n),
        reply_markup=get_captcha_settings_keyboard(chat, i18n),
        parse_mode="HTML",
    )
    await callback.answer(i18n.settings.updated())


@router.callback_query(SettingsCallback.filter(F.action == "captcha_timeout_menu"))
async def captcha_timeout_menu(callback: CallbackQuery, i18n: TranslatorRunner) -> None:
    """Показать выбор таймаута капчи."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    await callback.message.edit_text(
        i18n.settings.captcha.timeout.select(),
        reply_markup=get_captcha_timeout_keyboard(i18n),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(SettingsCallback.filter(F.action == "set_captcha_timeout"))
async def set_captcha_timeout(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    session: AsyncSession,
    i18n: TranslatorRunner,
    db_chat: Chat,
) -> None:
    """Установить таймаут капчи."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    try:
        seconds = int(callback_data.value)
    except (ValueError, TypeError):
        await callback.answer("Invalid timeout")
        return

    await record_settings_changes(session, db_chat, callback.from_user.id, {"captcha_timeout": seconds})
    chat = await update_chat_settings(session, db_chat.id, captcha_timeout=seconds)

    await callback.message.edit_text(
        _get_captcha_menu_text(chat, i18n),
        reply_markup=get_captcha_settings_keyboard(chat, i18n),
        parse_mode="HTML",
    )
    await callback.answer(i18n.settings.updated())


@router.callback_query(SettingsCallback.filter(F.action == "captcha_attempts_incr"))
async def captcha_attempts_incr(
    callback: CallbackQuery,
    session: AsyncSession,
    i18n: TranslatorRunner,
    db_chat: Chat,
) -> None:
    """Увеличить максимальное количество попыток капчи."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    new_value = min(db_chat.captcha_max_attempts + 1, 10)
    if new_value == db_chat.captcha_max_attempts:
        await callback.answer()
        return

    await record_settings_changes(session, db_chat, callback.from_user.id, {"captcha_max_attempts": new_value})
    chat = await update_chat_settings(session, db_chat.id, captcha_max_attempts=new_value)

    await callback.message.edit_text(
        _get_captcha_menu_text(chat, i18n),
        reply_markup=get_captcha_settings_keyboard(chat, i18n),
        parse_mode="HTML",
    )
    await callback.answer(i18n.settings.updated())


@router.callback_query(SettingsCallback.filter(F.action == "captcha_attempts_decr"))
async def captcha_attempts_decr(
    callback: CallbackQuery,
    session: AsyncSession,
    i18n: TranslatorRunner,
    db_chat: Chat,
) -> None:
    """Уменьшить максимальное количество попыток капчи."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    new_value = max(db_chat.captcha_max_attempts - 1, 1)
    if new_value == db_chat.captcha_max_attempts:
        await callback.answer()
        return

    await record_settings_changes(session, db_chat, callback.from_user.id, {"captcha_max_attempts": new_value})
    chat = await update_chat_settings(session, db_chat.id, captcha_max_attempts=new_value)

    await callback.message.edit_text(
        _get_captcha_menu_text(chat, i18n),
        reply_markup=get_captcha_settings_keyboard(chat, i18n),
        parse_mode="HTML",
    )
    await callback.answer(i18n.settings.updated())


@router.callback_query(SettingsCallback.filter(F.action == "captcha_ban_duration_menu"))
async def captcha_ban_duration_menu(callback: CallbackQuery, i18n: TranslatorRunner) -> None:
    """Показать выбор длительности бана за провал капчи."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    await callback.message.edit_text(
        i18n.settings.captcha.ban.select(),
        reply_markup=get_captcha_ban_duration_keyboard(i18n),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(SettingsCallback.filter(F.action == "set_captcha_ban_duration"))
async def set_captcha_ban_duration(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    session: AsyncSession,
    i18n: TranslatorRunner,
    db_chat: Chat,
) -> None:
    """Установить длительность бана за провал капчи."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    try:
        seconds = int(callback_data.value)
    except (ValueError, TypeError):
        await callback.answer("Invalid duration")
        return

    await record_settings_changes(session, db_chat, callback.from_user.id, {"captcha_ban_duration": seconds})
    chat = await update_chat_settings(session, db_chat.id, captcha_ban_duration=seconds)

    await callback.message.edit_text(
        _get_captcha_menu_text(chat, i18n),
        reply_markup=get_captcha_settings_keyboard(chat, i18n),
        parse_mode="HTML",
    )
    await callback.answer(i18n.settings.updated())


@router.callback_query(SettingsCallback.filter(F.action == "triggers_menu"))
async def triggers_menu(callback: CallbackQuery, i18n: TranslatorRunner, db_chat: Chat) -> None:
    """Показать подменю настроек триггеров."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    triggers_status = "✅" if db_chat.module_triggers else "❌"
    admins_status = "✅" if db_chat.admins_only_add else "❌"

    text = (
        f"{i18n.settings.triggers.title()}\n\n"
        f"{i18n.settings.triggers.module(status=triggers_status)}\n"
        f"{i18n.settings.triggers.admins(status=admins_status)}\n"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_triggers_settings_keyboard(db_chat, i18n),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(SettingsCallback.filter(F.action == "toggle_admins_only"))
async def toggle_admins_only(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    session: AsyncSession,
    i18n: TranslatorRunner,
    db_chat: Chat,
) -> None:
    """Переключить режим 'только админы'."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    new_value = not db_chat.admins_only_add
    await record_settings_changes(session, db_chat, callback.from_user.id, {"admins_only_add": new_value})
    chat = await update_chat_settings(session, db_chat.id, admins_only_add=new_value)

    # Возвращаемся в подменю триггеров
    triggers_status = "✅" if chat.module_triggers else "❌"
    admins_status = "✅" if chat.admins_only_add else "❌"

    text = (
        f"{i18n.settings.triggers.title()}\n\n"
        f"{i18n.settings.triggers.module(status=triggers_status)}\n"
        f"{i18n.settings.triggers.admins(status=admins_status)}\n"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_triggers_settings_keyboard(chat, i18n),
        parse_mode="HTML",
    )
    await callback.answer(i18n.settings.updated())


@router.callback_query(SettingsCallback.filter(F.action == "toggle_triggers"))
async def toggle_triggers(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    session: AsyncSession,
    i18n: TranslatorRunner,
    db_chat: Chat,
) -> None:
    """Переключить модуль триггеров."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    new_value = not db_chat.module_triggers
    await record_settings_changes(session, db_chat, callback.from_user.id, {"module_triggers": new_value})
    chat = await update_chat_settings(session, db_chat.id, module_triggers=new_value)

    # Возвращаемся в подменю триггеров
    triggers_status = "✅" if chat.module_triggers else "❌"
    admins_status = "✅" if chat.admins_only_add else "❌"

    text = (
        f"{i18n.settings.triggers.title()}\n\n"
        f"{i18n.settings.triggers.module(status=triggers_status)}\n"
        f"{i18n.settings.triggers.admins(status=admins_status)}\n"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_triggers_settings_keyboard(chat, i18n),
        parse_mode="HTML",
    )
    await callback.answer(i18n.settings.updated())


@router.callback_query(SettingsCallback.filter(F.action == "toggle_moderation"))
async def toggle_moderation(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    session: AsyncSession,
    i18n: TranslatorRunner,
    db_chat: Chat,
) -> None:
    """Переключить модуль модерации."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    new_value = not db_chat.module_moderation
    await record_settings_changes(session, db_chat, callback.from_user.id, {"module_moderation": new_value})
    chat = await update_chat_settings(session, db_chat.id, module_moderation=new_value)

    # Возвращаемся в подменю модерации
    keyboard = get_moderation_settings_keyboard(chat, i18n)
    await callback.message.edit_text(
        i18n.mod.settings.title(),
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML",
    )
    await callback.answer(i18n.settings.updated())


@router.callback_query(SettingsCallback.filter(F.action == "toggle_tags"))
async def toggle_tags(
    callback: CallbackQuery,
    session: AsyncSession,
    i18n: TranslatorRunner,
    db_chat: Chat,
) -> None:
    """Переключить систему тегов."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    new_value = not db_chat.tags_enabled

    # При включении — проверить, что у бота есть право can_manage_tags
    if new_value:
        bot_member = await callback.message.chat.get_member(bot.id)
        if bot_member.status != "administrator":
            await callback.answer(i18n.tags.bot.no.admin(), show_alert=True)
            return
        if not getattr(bot_member, "can_manage_tags", False):
            await callback.answer(i18n.tags.bot.no.permission(), show_alert=True)
            return

    await record_settings_changes(session, db_chat, callback.from_user.id, {"tags_enabled": new_value})
    chat = await update_chat_settings(session, db_chat.id, tags_enabled=new_value)
    await _update_settings_message(callback, chat, i18n)
    await callback.answer(i18n.settings.updated())


@router.callback_query(SettingsCallback.filter(F.action == "clear_ask"))
async def clear_ask(callback: CallbackQuery, i18n: TranslatorRunner) -> None:
    """Запрос подтверждения очистки всех триггеров."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    await callback.message.edit_text(
        i18n.confirm.clear(),
        reply_markup=get_clear_confirm_keyboard(i18n),
    )
    await callback.answer()


@router.callback_query(SettingsCallback.filter(F.action == "clear_confirm"))
async def clear_confirm(callback: CallbackQuery, session: AsyncSession, i18n: TranslatorRunner, db_chat: Chat) -> None:
    """Подтверждение очистки всех триггеров."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    count = await delete_all_triggers_by_chat(session, callback.message.chat.id)

    triggers_status = "✅" if db_chat.module_triggers else "❌"
    admins_status = "✅" if db_chat.admins_only_add else "❌"

    text = (
        f"{i18n.triggers.cleared.text(count=count)}\n\n"
        f"{i18n.settings.triggers.title()}\n\n"
        f"{i18n.settings.triggers.module(status=triggers_status)}\n"
        f"{i18n.settings.triggers.admins(status=admins_status)}\n"
    )

    await callback.message.edit_text(
        text,
        reply_markup=get_triggers_settings_keyboard(db_chat, i18n),
        parse_mode="HTML",
    )
    await callback.answer(i18n.triggers.cleared(count=count))


@router.callback_query(SettingsCallback.filter(F.action == "change_timezone"))
async def change_timezone(callback: CallbackQuery, i18n: TranslatorRunner, state: FSMContext) -> None:
    """Изменить таймзону."""
    await state.clear()
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="UTC",
                    callback_data=SettingsCallback(action="set_timezone", value="UTC").pack(),
                ),
                InlineKeyboardButton(
                    text="Europe/Moscow",
                    callback_data=SettingsCallback(
                        action="set_timezone",
                        value="Europe/Moscow",
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Europe/Kaliningrad",
                    callback_data=SettingsCallback(
                        action="set_timezone",
                        value="Europe/Kaliningrad",
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="Asia/Yekaterinburg",
                    callback_data=SettingsCallback(
                        action="set_timezone",
                        value="Asia/Yekaterinburg",
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Europe/Kyiv",
                    callback_data=SettingsCallback(
                        action="set_timezone",
                        value="Europe/Kyiv",
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=i18n.btn.custom.timezone(),
                    callback_data=SettingsCallback(
                        action="custom_timezone",
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=i18n.btn.back(),
                    callback_data=SettingsCallback(
                        action="settings_back",
                    ).pack(),
                ),
            ],
        ]
    )

    await callback.message.edit_text(
        i18n.settings.select.timezone(),
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(SettingsCallback.filter(F.action == "set_timezone"))
async def set_timezone(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    session: AsyncSession,
    i18n: TranslatorRunner,
    db_chat: Chat,
) -> None:
    """Установить таймзону."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    timezone = callback_data.value
    if not timezone:
        await callback.answer(i18n.error.invalid.timezone(), show_alert=True)
        return

    await record_settings_changes(session, db_chat, callback.from_user.id, {"timezone": timezone})
    chat = await update_chat_settings(session, db_chat.id, timezone=timezone)
    await _update_settings_message(callback, chat, i18n)
    await callback.answer(i18n.settings.updated())


@router.callback_query(SettingsCallback.filter(F.action == "custom_timezone"))
async def custom_timezone(callback: CallbackQuery, i18n: TranslatorRunner, state: FSMContext) -> None:
    """Ввести кастомную таймзону."""
    await state.set_state(SettingsStates.waiting_for_timezone)
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.btn.back(),
                    callback_data=SettingsCallback(action="change_timezone").pack(),
                ),
            ],
        ]
    )

    await callback.message.edit_text(
        i18n.settings.enter.timezone(),
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(SettingsStates.waiting_for_timezone, F.text.regexp(r"^[A-Za-z]+/[A-Za-z_]+$"))
async def handle_custom_timezone(
    message: Message, session: AsyncSession, i18n: TranslatorRunner, db_chat: Chat, state: FSMContext
) -> None:
    """Обработать введенную таймзону."""
    await state.clear()
    user_member = await message.chat.get_member(message.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        return

    timezone = message.text.strip()
    try:
        ZoneInfo(timezone)
    except Exception:
        await message.answer(i18n.error.invalid.timezone(), parse_mode="HTML")
        return

    await record_settings_changes(session, db_chat, message.from_user.id, {"timezone": timezone})
    await update_chat_settings(session, db_chat.id, timezone=timezone)
    await message.answer(i18n.settings.timezone.updated(timezone=timezone), parse_mode="HTML")


@router.message(Command("lang"))
async def lang_command(message: Message, i18n: TranslatorRunner) -> None:
    """Команда выбора языка."""
    user_member = await message.chat.get_member(message.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await message.answer(i18n.error.no.rights(), parse_mode="HTML")
        return

    await message.answer(
        i18n.lang.select.title(),
        reply_markup=get_language_keyboard(i18n, translator_hub),
        parse_mode="HTML",
    )


@router.callback_query(LanguageCallback.filter())
async def on_language_select(
    callback: CallbackQuery,
    callback_data: LanguageCallback,
    session: AsyncSession,
    i18n: TranslatorRunner,
    db_chat: Chat,
) -> None:
    """Обработчик выбора языка."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.error.no.rights(), show_alert=True)
        return

    lang_code = callback_data.code
    chat_id = callback.message.chat.id

    await record_settings_changes(session, db_chat, callback.from_user.id, {"language_code": lang_code})
    await update_language(session, chat_id, lang_code)

    await valkey.set(f"lang:{chat_id}", lang_code, ex=3600)

    new_i18n = translator_hub.get_translator_by_locale(lang_code)

    lang_name = new_i18n.lang.display.name()

    await callback.message.edit_text(new_i18n.settings.lang.changed(lang=lang_name), reply_markup=None)
    await callback.answer()


@router.message(Command("debug_captcha"))
async def debug_captcha_command(message: Message, session: AsyncSession, i18n: TranslatorRunner, user: User) -> None:
    """Создает тестовую сессию капчи для отладки."""
    if message.from_user.id not in settings.BOT_ADMINS and not user.is_bot_moderator:
        await message.answer(i18n.error.no.rights(), parse_mode="HTML")
        return

    if message.chat.type != ChatType.PRIVATE:
        await message.answer(i18n.error.private.only(), parse_mode="HTML")
        return

    expires_at = datetime.now().astimezone() + timedelta(minutes=10)

    captcha_session = ChatCaptchaSession(
        chat_id=message.from_user.id,
        user_id=message.from_user.id,
        expires_at=expires_at,
        message_id=0,
    )
    session.add(captcha_session)
    await session.commit()
    await session.refresh(captcha_session)

    url = URL(settings.WEBAPP_URL)
    if settings.URL_PREFIX:
        url = url / settings.URL_PREFIX.strip("/")
    url = url / "webapp"
    url = url.with_fragment("/captcha")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛡️ Open Debug Captcha",
                    web_app=WebAppInfo(url=str(url)),
                )
            ]
        ]
    )

    await message.answer(
        f"🛠️ Debug Captcha Session Created\n\n"
        f"Session ID: {captcha_session.id}\n"
        f"Expires: {expires_at.strftime('%H:%M:%S')}\n\n"
        f"Click the button below to test the captcha:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


def _fmt(val: object) -> str:
    """Format audit value for display."""
    if val is None:
        return "—"
    if isinstance(val, bool):
        return "✅" if val else "❌"
    if isinstance(val, (dict, list)):
        return "..."
    return str(val)


@router.message(Command("auditlog"))
async def auditlog_command(
    message: Message,
    session: AsyncSession,
    i18n: TranslatorRunner,
    db_chat: Chat,
) -> None:
    """Показать последние изменения настроек."""
    user_member = await message.chat.get_member(message.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await message.answer(i18n.error.no.rights(), parse_mode="HTML")
        return

    entries, _total = await get_audit_log(session, db_chat.id, page=1, limit=10)

    if not entries:
        await message.answer("📋 История изменений пуста.", parse_mode="HTML")
        return

    lines = ["📋 <b>Последние изменения настроек:</b>\n"]
    for entry in entries:
        dt = entry.created_at.strftime("%d.%m %H:%M")
        section = {
            "general": "Общие",
            "captcha": "Капча",
            "moderation": "Модерация",
            "triggers": "Триггеры",
            "tags": "Теги",
            "welcome": "Приветствие",
            "other": "Прочее",
        }.get(entry.section, entry.section)

        changes_text = ", ".join(f"{c['field']}: {_fmt(c['old'])} → {_fmt(c['new'])}" for c in entry.changes)
        lines.append(f"<code>{dt}</code> | {section}\n  {changes_text}")

    await message.answer("\n".join(lines), parse_mode="HTML")
