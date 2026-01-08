from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject
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

from app.bot.callback_data.admin import LanguageCallback, SettingsCallback
from app.bot.keyboards.admin import (
    get_clear_confirm_keyboard,
    get_language_keyboard,
    get_settings_keyboard,
)
from app.core.config import settings
from app.core.i18n import translator_hub
from app.core.valkey import valkey
from app.services.chat_service import (
    get_or_create_chat,
    update_chat_settings,
    update_language,
)
from app.services.trigger_service import (
    delete_all_triggers_by_chat,
    delete_trigger_by_key,
    get_trigger_by_key,
)

router = Router()


@router.message(Command("admin"))
async def admin_command(message: Message, i18n: TranslatorRunner) -> None:
    """Открыть админ-панель."""
    user_member = await message.chat.get_member(message.from_user.id)
    if user_member.status not in ("administrator", "creator") and message.from_user.id not in settings.BOT_ADMINS:
        await message.answer(i18n.get("error-no-rights"), parse_mode="HTML")
        return

    if message.chat.type != ChatType.PRIVATE:
        await message.answer(i18n.get("error-private-only"), parse_mode="HTML")
        return

    url = URL(settings.WEBAPP_URL)
    if settings.URL_PREFIX:
        url = url / settings.URL_PREFIX.strip("/")
    url = url / "webapp"

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
        await message.answer(i18n.get("del-usage"), parse_mode="HTML")
        return

    key_phrase = command.args

    trigger = await get_trigger_by_key(session, message.chat.id, key_phrase)
    if not trigger:
        await message.answer(i18n.get("trigger-not-found"), parse_mode="HTML")
        return

    user_member = await message.chat.get_member(message.from_user.id)
    is_admin = user_member.status in ("administrator", "creator")
    is_creator = trigger.created_by == message.from_user.id

    if not (is_admin or is_creator):
        await message.answer(i18n.get("error-no-rights"), parse_mode="HTML")
        return

    deleted = await delete_trigger_by_key(session, message.chat.id, key_phrase)
    if deleted:
        await message.answer(i18n.get("trigger-deleted"), parse_mode="HTML")
    else:
        await message.answer(i18n.get("trigger-delete-error"), parse_mode="HTML")


@router.message(Command("settings"))
async def settings_command(message: Message, session: AsyncSession, i18n: TranslatorRunner) -> None:
    """Показать настройки чата."""
    user_member = await message.chat.get_member(message.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await message.answer(i18n.get("error-no-rights"), parse_mode="HTML")
        return

    chat = await get_or_create_chat(session, message.chat.id)

    status = "✅" if chat.admins_only_add else "❌"
    trusted_status = i18n.get("settings-trusted") if chat.is_trusted else ""

    text = f"{i18n.get('settings-title')}\n\n{i18n.get('settings-admins-only', status=status)}\n"
    if trusted_status:
        text += f"\n{trusted_status}\n"

    await message.answer(text, reply_markup=get_settings_keyboard(chat.admins_only_add, i18n), parse_mode="HTML")


@router.callback_query(SettingsCallback.filter(F.action == "toggle_admins_only"))
async def toggle_admins_only(
    callback: CallbackQuery, callback_data: SettingsCallback, session: AsyncSession, i18n: TranslatorRunner
) -> None:
    """Переключить режим 'только админы'."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.get("error-no-rights"), show_alert=True)
        return

    chat = await get_or_create_chat(session, callback.message.chat.id)
    new_value = not chat.admins_only_add
    chat = await update_chat_settings(session, chat.id, admins_only_add=new_value)

    status = "✅" if chat.admins_only_add else "❌"
    trusted_status = i18n.get("settings-trusted") if chat.is_trusted else ""

    text = f"{i18n.get('settings-title')}\n\n{i18n.get('settings-admins-only', status=status)}\n"
    if trusted_status:
        text += f"\n{trusted_status}\n"

    await callback.message.edit_text(
        text, reply_markup=get_settings_keyboard(chat.admins_only_add, i18n), parse_mode="HTML"
    )
    await callback.answer(i18n.get("settings-updated"))


@router.callback_query(SettingsCallback.filter(F.action == "clear_ask"))
async def clear_ask(callback: CallbackQuery, i18n: TranslatorRunner) -> None:
    """Запрос подтверждения очистки всех триггеров."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.get("error-no-rights"), show_alert=True)
        return

    await callback.message.edit_text(
        i18n.get("confirm-clear"),
        reply_markup=get_clear_confirm_keyboard(i18n),
    )
    await callback.answer()


@router.callback_query(SettingsCallback.filter(F.action == "clear_confirm"))
async def clear_confirm(callback: CallbackQuery, session: AsyncSession, i18n: TranslatorRunner) -> None:
    """Подтверждение очистки всех триггеров."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.get("error-no-rights"), show_alert=True)
        return

    count = await delete_all_triggers_by_chat(session, callback.message.chat.id)

    chat = await get_or_create_chat(session, callback.message.chat.id)

    status = "✅" if chat.admins_only_add else "❌"
    trusted_status = i18n.get("settings-trusted") if chat.is_trusted else ""

    text = f"{i18n.get('settings-title')}\n\n{i18n.get('settings-admins-only', status=status)}\n"
    if trusted_status:
        text += f"\n{trusted_status}\n"

    text += f"\n{i18n.get('triggers-cleared-text', count=count)}"

    await callback.message.edit_text(
        text, reply_markup=get_settings_keyboard(chat.admins_only_add, i18n), parse_mode="HTML"
    )
    await callback.answer(i18n.get("triggers-cleared", count=count))


@router.callback_query(SettingsCallback.filter(F.action == "settings_back"))
async def settings_back(callback: CallbackQuery, session: AsyncSession, i18n: TranslatorRunner) -> None:
    """Возврат в меню настроек."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.get("error-no-rights"), show_alert=True)
        return

    chat = await get_or_create_chat(session, callback.message.chat.id)

    status = "✅" if chat.admins_only_add else "❌"
    trusted_status = i18n.get("settings-trusted") if chat.is_trusted else ""

    text = f"{i18n.get('settings-title')}\n\n{i18n.get('settings-admins-only', status=status)}\n"
    if trusted_status:
        text += f"\n{trusted_status}\n"

    await callback.message.edit_text(
        text, reply_markup=get_settings_keyboard(chat.admins_only_add, i18n), parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(SettingsCallback.filter(F.action == "close"))
async def close_settings(callback: CallbackQuery) -> None:
    """Закрыть меню настроек."""
    await callback.message.delete()
    await callback.answer()


@router.message(Command("lang"))
async def lang_command(message: Message, i18n: TranslatorRunner) -> None:
    """Команда выбора языка."""
    user_member = await message.chat.get_member(message.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await message.answer(i18n.get("error-no-rights"), parse_mode="HTML")
        return

    await message.answer(i18n.get("lang-select-title"), reply_markup=get_language_keyboard(i18n), parse_mode="HTML")


@router.callback_query(LanguageCallback.filter())
async def on_language_select(
    callback: CallbackQuery, callback_data: LanguageCallback, session: AsyncSession, i18n: TranslatorRunner
) -> None:
    """Обработчик выбора языка."""
    user_member = await callback.message.chat.get_member(callback.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await callback.answer(i18n.get("error-no-rights"), show_alert=True)
        return

    lang_code = callback_data.code
    chat_id = callback.message.chat.id

    await update_language(session, chat_id, lang_code)

    await valkey.set(f"lang:{chat_id}", lang_code, ex=3600)

    new_i18n = translator_hub.get_translator_by_locale(lang_code)

    lang_name = "English" if lang_code == "en" else "Русский"

    await callback.message.edit_text(new_i18n.get("settings-lang-changed", lang=lang_name), reply_markup=None)
    await callback.answer()
