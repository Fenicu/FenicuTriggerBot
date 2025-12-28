import math

from aiogram import Bot, Router, html
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from fluentogram import TranslatorRunner
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callback_data.triggers import TriggerEditCallback, TriggersListCallback
from app.bot.keyboards.triggers import (
    get_delete_confirm_keyboard,
    get_trigger_edit_keyboard,
    get_triggers_list_keyboard,
)
from app.db.models.trigger import AccessLevel, MatchType, Trigger
from app.services import trigger_service

router = Router()

PAGE_SIZE = 10


def format_triggers_list(
    triggers: list[Trigger], page: int, total_pages: int, total_count: int, i18n: TranslatorRunner
) -> str:
    """Форматирование списка триггеров."""
    if not triggers:
        return i18n.get("trigger-list-empty")

    header = i18n.get("trigger-list-header", count=total_count)
    lines = [f"{header}\n"]
    for i, t in enumerate(triggers):
        idx = (page - 1) * PAGE_SIZE + i + 1
        match_icon = {MatchType.EXACT: "=", MatchType.CONTAINS: "≈", MatchType.REGEXP: ".*"}.get(t.match_type, "?")
        lines.append(f"{idx}. <code>{html.quote(t.key_phrase)}</code> ({match_icon})")

    page_info = i18n.get("trigger-list-page", page=page, total=total_pages)
    lines.append(f"\n{page_info}")
    return "\n".join(lines)


def format_trigger_details(trigger: Trigger, i18n: TranslatorRunner, creator_name: str) -> str:
    """Форматирование деталей триггера."""
    title = i18n.get("trigger-edit-title")
    key = i18n.get("trigger-edit-key", trigger_key=html.quote(trigger.key_phrase))
    type_ = i18n.get("trigger-edit-type", type=trigger.match_type.value)

    case_val_key = "val-case-sensitive" if trigger.is_case_sensitive else "val-case-insensitive"
    case = i18n.get("trigger-edit-case", value=i18n.get(case_val_key))

    access_val_key = {
        AccessLevel.ALL: "val-access-all",
        AccessLevel.ADMINS: "val-access-admins",
        AccessLevel.OWNER: "val-access-owner",
    }.get(trigger.access_level, "val-access-all")
    access = i18n.get("trigger-edit-access", value=i18n.get(access_val_key))

    created = i18n.get("trigger-edit-created", user=html.quote(creator_name))
    stats = i18n.get("trigger-edit-stats", count=trigger.usage_count)

    return f"{title}\n{key}\n{type_}\n{case}\n{access}\n{stats}\n{created}"


@router.message(Command("triggers"))
async def cmd_triggers(message: Message, session: AsyncSession, i18n: TranslatorRunner) -> None:
    """Показать список триггеров."""
    chat_id = message.chat.id
    triggers, total_count = await trigger_service.get_triggers_paginated(session, chat_id, page=1, page_size=PAGE_SIZE)

    if not triggers:
        await message.answer(i18n.get("trigger-list-empty"), parse_mode="HTML")
        return

    total_pages = math.ceil(total_count / PAGE_SIZE)
    text = format_triggers_list(triggers, 1, total_pages, total_count, i18n)
    keyboard = get_triggers_list_keyboard(triggers, 1, total_pages)

    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(TriggersListCallback.filter())
async def on_triggers_list(
    callback: CallbackQuery, callback_data: TriggersListCallback, session: AsyncSession, i18n: TranslatorRunner
) -> None:
    """Обработчик навигации по списку триггеров."""
    chat_id = callback.message.chat.id
    page = callback_data.page

    triggers, total_count = await trigger_service.get_triggers_paginated(
        session, chat_id, page=page, page_size=PAGE_SIZE
    )

    if not triggers and page > 1:
        page = 1
        triggers, total_count = await trigger_service.get_triggers_paginated(
            session, chat_id, page=page, page_size=PAGE_SIZE
        )

    total_pages = math.ceil(total_count / PAGE_SIZE) if total_count > 0 else 1
    text = format_triggers_list(triggers, page, total_pages, total_count, i18n)
    keyboard = get_triggers_list_keyboard(triggers, page, total_pages)

    if callback.message.text != text or callback.message.reply_markup != keyboard:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    await callback.answer()


@router.callback_query(TriggerEditCallback.filter())
async def on_trigger_edit(
    callback: CallbackQuery, callback_data: TriggerEditCallback, session: AsyncSession, bot: Bot, i18n: TranslatorRunner
) -> None:
    """Обработчик редактирования триггера."""
    trigger_id = callback_data.id
    action = callback_data.action
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id

    if action == "back":
        await on_triggers_list(callback, TriggersListCallback(page=1), session, i18n)
        return

    trigger = await trigger_service.get_trigger_by_id(session, trigger_id)

    if not trigger:
        await callback.answer(i18n.get("trigger-not-found"), show_alert=True)
        await on_triggers_list(callback, TriggersListCallback(page=1), session, i18n)
        return

    member = await bot.get_chat_member(chat_id, user_id)
    is_admin = member.status in ["creator", "administrator"]
    is_creator = trigger.created_by == user_id

    if not (is_admin or is_creator):
        await callback.answer(i18n.get("error-no-rights"), show_alert=True)
        return

    try:
        creator_chat = await bot.get_chat(trigger.created_by)
        creator_name = creator_chat.username or creator_chat.full_name
    except Exception:
        creator_name = str(trigger.created_by)

    if action == "open":
        text = format_trigger_details(trigger, i18n, creator_name)
        keyboard = get_trigger_edit_keyboard(trigger, i18n)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    elif action == "toggle_case":
        await trigger_service.update_trigger(session, trigger.id, is_case_sensitive=not trigger.is_case_sensitive)
        trigger = await trigger_service.get_trigger_by_id(session, trigger_id)
        text = format_trigger_details(trigger, i18n, creator_name)
        keyboard = get_trigger_edit_keyboard(trigger, i18n)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    elif action == "toggle_type":
        new_type = {
            MatchType.EXACT: MatchType.CONTAINS,
            MatchType.CONTAINS: MatchType.REGEXP,
            MatchType.REGEXP: MatchType.EXACT,
        }.get(trigger.match_type, MatchType.EXACT)

        await trigger_service.update_trigger(session, trigger.id, match_type=new_type)
        trigger = await trigger_service.get_trigger_by_id(session, trigger_id)
        text = format_trigger_details(trigger, i18n, creator_name)
        keyboard = get_trigger_edit_keyboard(trigger, i18n)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    elif action == "toggle_access":
        new_access = {
            AccessLevel.ALL: AccessLevel.ADMINS,
            AccessLevel.ADMINS: AccessLevel.OWNER,
            AccessLevel.OWNER: AccessLevel.ALL,
        }.get(trigger.access_level, AccessLevel.ALL)

        await trigger_service.update_trigger(session, trigger.id, access_level=new_access)
        trigger = await trigger_service.get_trigger_by_id(session, trigger_id)
        text = format_trigger_details(trigger, i18n, creator_name)
        keyboard = get_trigger_edit_keyboard(trigger, i18n)
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    elif action == "delete_ask":
        keyboard = get_delete_confirm_keyboard(trigger.id, i18n)
        await callback.message.edit_text(
            i18n.get("confirm-delete", trigger_key=html.quote(trigger.key_phrase)),
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    elif action == "delete_confirm":
        await trigger_service.delete_trigger_by_id(session, trigger.id)
        await callback.answer(i18n.get("trigger-deleted"))
        await on_triggers_list(callback, TriggersListCallback(page=1), session, i18n)

    await callback.answer()
