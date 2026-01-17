from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from fluentogram import TranslatorRunner

from app.bot.callback_data.admin import LanguageCallback, SettingsCallback
from app.bot.callback_data.moderation import ModerationSettingsCallback


def get_settings_keyboard(
    admins_only_add: bool,
    captcha_enabled: bool,
    module_triggers: bool,
    module_moderation: bool,
    timezone: str,
    i18n: TranslatorRunner,
) -> InlineKeyboardMarkup:
    """Клавиатура настроек."""
    builder = InlineKeyboardBuilder()

    builder.button(text="👮‍♂️ Модерация и Варны", callback_data=ModerationSettingsCallback(action="menu"))

    toggle_key = "btn-admins-only-true" if admins_only_add else "btn-admins-only-false"
    builder.button(text=i18n.get(toggle_key), callback_data=SettingsCallback(action="toggle_admins_only"))

    captcha_key = "btn-captcha-true" if captcha_enabled else "btn-captcha-false"
    builder.button(text=i18n.get(captcha_key), callback_data=SettingsCallback(action="toggle_captcha"))

    triggers_key = "btn-triggers-true" if module_triggers else "btn-triggers-false"
    builder.button(text=i18n.get(triggers_key), callback_data=SettingsCallback(action="toggle_triggers"))

    moderation_key = "btn-moderation-true" if module_moderation else "btn-moderation-false"
    builder.button(text=i18n.get(moderation_key), callback_data=SettingsCallback(action="toggle_moderation"))

    builder.button(text=f"🌍 {timezone}", callback_data=SettingsCallback(action="change_timezone"))

    builder.button(text=i18n.get("btn-clear-triggers"), callback_data=SettingsCallback(action="clear_ask"))
    builder.button(text=i18n.get("btn-close"), callback_data=SettingsCallback(action="close"))

    builder.adjust(1)
    return builder.as_markup()


def get_clear_confirm_keyboard(i18n: TranslatorRunner) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения очистки."""
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n.get("action-yes"), callback_data=SettingsCallback(action="clear_confirm"))
    builder.button(text=i18n.get("action-cancel"), callback_data=SettingsCallback(action="settings_back"))
    return builder.as_markup()


def get_language_keyboard(i18n: TranslatorRunner) -> InlineKeyboardMarkup:
    """Клавиатура выбора языка."""
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n.get("btn-lang-ru"), callback_data=LanguageCallback(code="ru"))
    builder.button(text=i18n.get("btn-lang-en"), callback_data=LanguageCallback(code="en"))
    builder.button(text=i18n.get("btn-close"), callback_data=SettingsCallback(action="close"))
    builder.adjust(2, 1)
    return builder.as_markup()
