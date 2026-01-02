from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callback_data.admin import SettingsCallback
from app.bot.callback_data.moderation import ModerationSettingsCallback
from app.db.models.chat import Chat


def format_duration(seconds: int) -> str:
    if seconds == 0:
        return "Навсегда"

    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} мин."

    hours = minutes // 60
    if hours < 24:
        return f"{hours} ч."

    days = hours // 24
    if days < 7:
        return f"{days} дн."

    weeks = days // 7
    return f"{weeks} нед."


def get_moderation_settings_keyboard(chat: Chat) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()

    builder.button(text="➖", callback_data=ModerationSettingsCallback(action="limit", value="decr"))
    builder.button(
        text=str(chat.warn_limit),
        callback_data="noop",
    )
    builder.button(text="➕", callback_data=ModerationSettingsCallback(action="limit", value="incr"))

    punishment_text = "🔨 Бан" if chat.warn_punishment == "ban" else "🔇 Мут"
    builder.button(
        text=f"Наказание: {punishment_text}",
        callback_data=ModerationSettingsCallback(action="punishment", value="toggle"),
    )

    duration_text = format_duration(chat.warn_duration)
    builder.button(
        text=f"⏳ Длительность: {duration_text}",
        callback_data=ModerationSettingsCallback(action="duration", value="menu"),
    )

    builder.button(
        text="« Назад",
        callback_data=SettingsCallback(action="settings_back"),
    )

    builder.adjust(3, 1, 1, 1)
    return builder


def get_duration_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()

    durations = [
        ("Навсегда", 0),
        ("10 минут", 600),
        ("1 час", 3600),
        ("1 сутки", 86400),
        ("1 неделя", 604800),
    ]

    for text, seconds in durations:
        builder.button(text=text, callback_data=ModerationSettingsCallback(action="duration", value=str(seconds)))

    builder.button(
        text="« Назад",
        callback_data=ModerationSettingsCallback(action="menu"),
    )

    builder.adjust(1)
    return builder
