from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from fluentogram import TranslatorRunner

from app.bot.callback_data.triggers import TriggerEditCallback, TriggersListCallback
from app.db.models.trigger import AccessLevel, MatchType, Trigger


def get_triggers_list_keyboard(triggers: list[Trigger], page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Клавиатура списка триггеров."""
    builder = InlineKeyboardBuilder()

    for i, trigger in enumerate(triggers):
        builder.button(text=str(i + 1), callback_data=TriggerEditCallback(id=trigger.id, action="open"))

    builder.adjust(5)

    nav_builder = InlineKeyboardBuilder()
    if page > 1:
        nav_builder.button(text="⬅️", callback_data=TriggersListCallback(page=page - 1))

    nav_builder.button(text=f"{page}/{total_pages}", callback_data="ignore")

    if page < total_pages:
        nav_builder.button(text="➡️", callback_data=TriggersListCallback(page=page + 1))

    builder.attach(nav_builder)

    return builder.as_markup()


def get_trigger_edit_keyboard(trigger: Trigger, i18n: TranslatorRunner) -> InlineKeyboardMarkup:
    """Клавиатура редактирования триггера."""
    builder = InlineKeyboardBuilder()

    case_key = "btn-case-sensitive" if trigger.is_case_sensitive else "btn-case-insensitive"
    builder.button(text=i18n.get(case_key), callback_data=TriggerEditCallback(id=trigger.id, action="toggle_case"))

    match_key = {
        MatchType.EXACT: "btn-match-exact",
        MatchType.CONTAINS: "btn-match-contains",
        MatchType.REGEXP: "btn-match-regexp",
    }.get(trigger.match_type, "btn-match-exact")

    builder.button(text=i18n.get(match_key), callback_data=TriggerEditCallback(id=trigger.id, action="toggle_type"))

    access_key = {
        AccessLevel.ALL: "btn-access-all",
        AccessLevel.ADMINS: "btn-access-admins",
        AccessLevel.OWNER: "btn-access-owner",
    }.get(trigger.access_level, "btn-access-all")

    builder.button(text=i18n.get(access_key), callback_data=TriggerEditCallback(id=trigger.id, action="toggle_access"))

    template_key = "btn-template-true" if trigger.is_template else "btn-template-false"
    builder.button(
        text=i18n.get(template_key), callback_data=TriggerEditCallback(id=trigger.id, action="toggle_template")
    )

    builder.button(text=i18n.get("btn-delete"), callback_data=TriggerEditCallback(id=trigger.id, action="delete_ask"))
    builder.button(text=i18n.get("btn-back"), callback_data=TriggersListCallback(page=1))

    builder.adjust(1, 1, 1, 2)

    return builder.as_markup()


def get_delete_confirm_keyboard(trigger_id: int, i18n: TranslatorRunner) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения удаления триггера."""
    builder = InlineKeyboardBuilder()

    builder.button(
        text=i18n.get("action-yes"), callback_data=TriggerEditCallback(id=trigger_id, action="delete_confirm")
    )
    builder.button(text=i18n.get("action-cancel"), callback_data=TriggerEditCallback(id=trigger_id, action="open"))

    return builder.as_markup()
