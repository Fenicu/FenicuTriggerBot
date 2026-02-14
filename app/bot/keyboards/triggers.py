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

    case_text = i18n.btn.case.sensitive() if trigger.is_case_sensitive else i18n.btn.case.insensitive()
    builder.button(text=case_text, callback_data=TriggerEditCallback(id=trigger.id, action="toggle_case"))

    match_text = {
        MatchType.EXACT: i18n.btn.matchtype.exact(),
        MatchType.CONTAINS: i18n.btn.matchtype.contains(),
        MatchType.REGEXP: i18n.btn.matchtype.regexp(),
    }.get(trigger.match_type, i18n.btn.matchtype.exact())

    builder.button(text=match_text, callback_data=TriggerEditCallback(id=trigger.id, action="toggle_type"))

    access_text = {
        AccessLevel.ALL: i18n.btn.access.all(),
        AccessLevel.ADMINS: i18n.btn.access.admins(),
        AccessLevel.OWNER: i18n.btn.access.owner(),
    }.get(trigger.access_level, i18n.btn.access.all())

    builder.button(text=access_text, callback_data=TriggerEditCallback(id=trigger.id, action="toggle_access"))

    template_text = i18n.btn.template.true() if trigger.is_template else i18n.btn.template.false()
    builder.button(
        text=template_text, callback_data=TriggerEditCallback(id=trigger.id, action="toggle_template")
    )

    builder.button(text=i18n.btn.delete(), callback_data=TriggerEditCallback(id=trigger.id, action="delete_ask"))
    builder.button(text=i18n.btn.back(), callback_data=TriggersListCallback(page=1))

    builder.adjust(1, 1, 1, 2)

    return builder.as_markup()


def get_delete_confirm_keyboard(trigger_id: int, i18n: TranslatorRunner) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения удаления триггера."""
    builder = InlineKeyboardBuilder()

    builder.button(
        text=i18n.action.yes(), callback_data=TriggerEditCallback(id=trigger_id, action="delete_confirm")
    )
    builder.button(text=i18n.action.cancel(), callback_data=TriggerEditCallback(id=trigger_id, action="open"))

    return builder.as_markup()
