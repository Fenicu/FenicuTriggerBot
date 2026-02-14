from aiogram.utils.keyboard import InlineKeyboardBuilder
from fluentogram import TranslatorRunner

from app.bot.callback_data.admin import SettingsCallback
from app.bot.callback_data.moderation import ModerationSettingsCallback
from app.db.models.chat import Chat


def format_duration(seconds: int, i18n: TranslatorRunner) -> str:
    if seconds == 0:
        return i18n.mod.duration.forever()

    minutes = seconds // 60
    if minutes < 60:
        return i18n.mod.duration.min(count=minutes)

    hours = minutes // 60
    if hours < 24:
        return i18n.mod.duration.hour(count=hours)

    days = hours // 24
    if days < 7:
        return i18n.mod.duration.day(count=days)

    weeks = days // 7
    return i18n.mod.duration.week(count=weeks)


def get_moderation_settings_keyboard(chat: Chat, i18n: TranslatorRunner) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()

    text = i18n.btn.moderation.true() if chat.module_moderation else i18n.btn.moderation.false()
    builder.button(text=text, callback_data=SettingsCallback(action="toggle_moderation"))

    builder.button(text="➖", callback_data=ModerationSettingsCallback(action="limit", value="decr"))
    builder.button(
        text=str(chat.warn_limit),
        callback_data="noop",
    )
    builder.button(text="➕", callback_data=ModerationSettingsCallback(action="limit", value="incr"))

    punishment_text = (
        i18n.mod.punishment.ban() if chat.warn_punishment == "ban" else i18n.mod.punishment.mute()
    )
    builder.button(
        text=i18n.mod.punishment.btn(punishment=punishment_text),
        callback_data=ModerationSettingsCallback(action="punishment", value="toggle"),
    )

    duration_text = format_duration(chat.warn_duration, i18n)
    builder.button(
        text=i18n.mod.duration.btn(duration=duration_text),
        callback_data=ModerationSettingsCallback(action="duration", value="menu"),
    )

    gban_status = "✅" if chat.gban_enabled else "❌"
    builder.button(
        text=i18n.moderation.gban.toggle(status=gban_status),
        callback_data=ModerationSettingsCallback(action="gban", value="toggle"),
    )

    builder.button(
        text=i18n.btn.back(),
        callback_data=SettingsCallback(action="settings_back"),
    )

    builder.adjust(1, 3, 1, 1, 1, 1)
    return builder


def get_duration_keyboard(i18n: TranslatorRunner) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()

    durations = [
        (i18n.mod.duration.forever(), 0),
        (i18n.mod.duration.tenmin(), 600),
        (i18n.mod.duration.onehour(), 3600),
        (i18n.mod.duration.oneday(), 86400),
        (i18n.mod.duration.oneweek(), 604800),
    ]

    for text, seconds in durations:
        builder.button(text=text, callback_data=ModerationSettingsCallback(action="duration", value=str(seconds)))

    builder.button(
        text=i18n.btn.back(),
        callback_data=ModerationSettingsCallback(action="menu"),
    )

    builder.adjust(1)
    return builder
