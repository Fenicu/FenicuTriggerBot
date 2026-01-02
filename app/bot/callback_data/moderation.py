from aiogram.filters.callback_data import CallbackData


class ModerationSettingsCallback(CallbackData, prefix="mod"):
    action: str
    value: str | None = None
