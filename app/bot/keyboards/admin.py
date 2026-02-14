from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from fluentogram import TranslatorHub, TranslatorRunner

from app.bot.callback_data.admin import CaptchaTypeCallback, LanguageCallback, SettingsCallback
from app.bot.callback_data.moderation import ModerationSettingsCallback
from app.core.i18n import available_locales


def get_settings_keyboard(
    admins_only_add: bool,
    captcha_enabled: bool,
    module_triggers: bool,
    module_moderation: bool,
    timezone: str,
    i18n: TranslatorRunner,
    captcha_type: str = "emoji",
) -> InlineKeyboardMarkup:
    """Клавиатура настроек."""
    builder = InlineKeyboardBuilder()

    builder.button(text=i18n.btn.moderation.warns(), callback_data=ModerationSettingsCallback(action="menu"))

    text = i18n.btn.admins.only.true() if admins_only_add else i18n.btn.admins.only.false()
    builder.button(text=text, callback_data=SettingsCallback(action="toggle_admins_only"))

    text = i18n.btn.captcha.true() if captcha_enabled else i18n.btn.captcha.false()
    builder.button(text=text, callback_data=SettingsCallback(action="toggle_captcha"))

    if captcha_enabled:
        emoji_text = (
            f"✅ {i18n.settings.captcha.type.emoji()}"
            if captcha_type == "emoji"
            else i18n.settings.captcha.type.emoji()
        )
        webapp_text = (
            f"✅ {i18n.settings.captcha.type.webapp()}"
            if captcha_type == "webapp"
            else i18n.settings.captcha.type.webapp()
        )
        builder.button(text=emoji_text, callback_data=CaptchaTypeCallback(type="emoji"))
        builder.button(text=webapp_text, callback_data=CaptchaTypeCallback(type="webapp"))

    text = i18n.btn.triggers.true() if module_triggers else i18n.btn.triggers.false()
    builder.button(text=text, callback_data=SettingsCallback(action="toggle_triggers"))

    text = i18n.btn.moderation.true() if module_moderation else i18n.btn.moderation.false()
    builder.button(text=text, callback_data=SettingsCallback(action="toggle_moderation"))

    builder.button(text=f"🌍 {timezone}", callback_data=SettingsCallback(action="change_timezone"))

    builder.button(text=i18n.btn.clear.triggers(), callback_data=SettingsCallback(action="clear_ask"))
    builder.button(text=i18n.btn.close(), callback_data=SettingsCallback(action="close"))

    if captcha_enabled:
        builder.adjust(1, 1, 1, 2, 1, 1, 1, 1, 1)
    else:
        builder.adjust(1)
    return builder.as_markup()


def get_clear_confirm_keyboard(i18n: TranslatorRunner) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения очистки."""
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n.action.yes(), callback_data=SettingsCallback(action="clear_confirm"))
    builder.button(text=i18n.action.cancel(), callback_data=SettingsCallback(action="settings_back"))
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
