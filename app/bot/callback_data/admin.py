from aiogram.filters.callback_data import CallbackData


class SettingsCallback(CallbackData, prefix="settings"):
    """Callback data для настроек."""

    action: str
    value: str | None = None


class LanguageCallback(CallbackData, prefix="lang"):
    """Callback data для выбора языка."""

    code: str


class CaptchaTypeCallback(CallbackData, prefix="captcha_type"):
    """Callback data для выбора типа капчи."""

    type: str
