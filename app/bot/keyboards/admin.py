from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from fluentogram import TranslatorHub, TranslatorRunner

from app.bot.callback_data.admin import CaptchaTypeCallback, LanguageCallback, SettingsCallback
from app.bot.callback_data.moderation import ModerationSettingsCallback
from app.bot.keyboards.moderation import format_duration
from app.core.i18n import available_locales
from app.db.models.chat import Chat


def get_settings_keyboard(chat: Chat, i18n: TranslatorRunner) -> InlineKeyboardMarkup:
    """Главное меню настроек (секционное)."""
    builder = InlineKeyboardBuilder()

    builder.button(text=i18n.btn.captcha.settings(), callback_data=SettingsCallback(action="captcha_menu"))
    builder.button(text=i18n.btn.moderation.warns(), callback_data=ModerationSettingsCallback(action="menu"))
    builder.button(text=i18n.btn.triggers.settings(), callback_data=SettingsCallback(action="triggers_menu"))
    builder.button(text=f"🌍 {chat.timezone}", callback_data=SettingsCallback(action="change_timezone"))
    builder.button(text=i18n.btn.close(), callback_data=SettingsCallback(action="close"))

    builder.adjust(1)
    return builder.as_markup()


def get_captcha_settings_keyboard(chat: Chat, i18n: TranslatorRunner) -> InlineKeyboardMarkup:
    """Подменю настроек капчи."""
    builder = InlineKeyboardBuilder()

    text = i18n.btn.captcha.true() if chat.captcha_enabled else i18n.btn.captcha.false()
    builder.button(text=text, callback_data=SettingsCallback(action="toggle_captcha"))

    if chat.captcha_enabled:
        emoji_text = (
            f"✅ {i18n.settings.captcha.type.emoji()}"
            if chat.captcha_type == "emoji"
            else i18n.settings.captcha.type.emoji()
        )
        webapp_text = (
            f"✅ {i18n.settings.captcha.type.webapp()}"
            if chat.captcha_type == "webapp"
            else i18n.settings.captcha.type.webapp()
        )
        builder.button(text=emoji_text, callback_data=CaptchaTypeCallback(type="emoji"))
        builder.button(text=webapp_text, callback_data=CaptchaTypeCallback(type="webapp"))

        timeout_text = format_duration(chat.captcha_timeout, i18n)
        builder.button(
            text=i18n.btn.captcha.timeout(timeout=timeout_text),
            callback_data=SettingsCallback(action="captcha_timeout_menu"),
        )

    builder.button(text=i18n.btn.back(), callback_data=SettingsCallback(action="settings_back"))

    if chat.captcha_enabled:
        builder.adjust(1, 2, 1, 1)
    else:
        builder.adjust(1)
    return builder.as_markup()


def get_captcha_timeout_keyboard(i18n: TranslatorRunner) -> InlineKeyboardMarkup:
    """Клавиатура выбора таймаута капчи."""
    builder = InlineKeyboardBuilder()

    timeouts = [
        (i18n.get("captcha-timeout-1min"), 60),
        (i18n.get("captcha-timeout-2min"), 120),
        (i18n.get("captcha-timeout-5min"), 300),
        (i18n.get("captcha-timeout-10min"), 600),
    ]

    for text, seconds in timeouts:
        builder.button(text=text, callback_data=SettingsCallback(action="set_captcha_timeout", value=str(seconds)))

    builder.button(text=i18n.btn.back(), callback_data=SettingsCallback(action="captcha_menu"))

    builder.adjust(1)
    return builder.as_markup()


def get_triggers_settings_keyboard(chat: Chat, i18n: TranslatorRunner) -> InlineKeyboardMarkup:
    """Подменю настроек триггеров."""
    builder = InlineKeyboardBuilder()

    text = i18n.btn.triggers.true() if chat.module_triggers else i18n.btn.triggers.false()
    builder.button(text=text, callback_data=SettingsCallback(action="toggle_triggers"))

    text = i18n.btn.admins.only.true() if chat.admins_only_add else i18n.btn.admins.only.false()
    builder.button(text=text, callback_data=SettingsCallback(action="toggle_admins_only"))

    builder.button(text=i18n.btn.clear.triggers(), callback_data=SettingsCallback(action="clear_ask"))
    builder.button(text=i18n.btn.back(), callback_data=SettingsCallback(action="settings_back"))

    builder.adjust(1)
    return builder.as_markup()


def get_clear_confirm_keyboard(i18n: TranslatorRunner) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения очистки."""
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n.action.yes(), callback_data=SettingsCallback(action="clear_confirm"))
    builder.button(text=i18n.action.cancel(), callback_data=SettingsCallback(action="triggers_menu"))
    return builder.as_markup()


def get_language_keyboard(i18n: TranslatorRunner, translator_hub: TranslatorHub) -> InlineKeyboardMarkup:
    """Клавиатура выбора языка."""
    builder = InlineKeyboardBuilder()
    for locale in available_locales:
        t = translator_hub.get_translator_by_locale(locale)
        builder.button(text=t.lang.display.name(), callback_data=LanguageCallback(code=locale))
    builder.button(text=i18n.btn.close(), callback_data=SettingsCallback(action="close"))
    builder.adjust(len(available_locales), 1)
    return builder.as_markup()
