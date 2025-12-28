from aiogram.filters.callback_data import CallbackData


class TriggersListCallback(CallbackData, prefix="triggers_list"):
    """Callback data для списка триггеров."""
    page: int


class TriggerEditCallback(CallbackData, prefix="trigger_edit"):
    """Callback data для редактирования триггера."""
    id: int
    action: str
