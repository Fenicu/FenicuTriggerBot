"""Wizard в личных сообщениях для создания триггеров.

Точки входа:
- /newtrigger в групповом чате — URL-кнопка с deep-link в ЛС.
- /newtrigger в ЛС — wizard стартует с шага choosing_chat.
- /start newtrigger_<chat_id> в ЛС — wizard стартует с awaiting_content.

FSM-states: choosing_chat → awaiting_content → awaiting_key → configuring_flags → confirming.
Авторизация: live get_chat_member в 3 точках (deep-link entry, nt:chat:<id>, перед save).
Concurrent save защищён локом `nt:save_lock:<user_id>` (SETNX TTL 10с) + Lua compare-and-delete.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from fluentogram import TranslatorRunner

from app.db.models.chat import Chat

logger = logging.getLogger(__name__)


# ─── Routers ──────────────────────────────────────────────────────────────────

dm_router = Router(name="creation_private_dm")
dm_router.message.filter(F.chat.type == "private")
dm_router.callback_query.filter(F.message.chat.type == "private")

group_router = Router(name="creation_private_group")
# group filter применяется на уровне родительского group_router в dispatcher.py


# ─── States & Callback data ───────────────────────────────────────────────────


class NewTriggerStates(StatesGroup):
    choosing_chat = State()
    awaiting_content = State()
    awaiting_key = State()
    configuring_flags = State()
    confirming = State()


class NewTriggerCB(CallbackData, prefix="nt"):
    action: str
    value: str = ""


# ─── Constants ────────────────────────────────────────────────────────────────

DEEP_LINK_PREFIX = "newtrigger_"
CHATS_PER_PAGE = 8
SAVE_LOCK_TTL = 10  # секунд
FSM_TTL = 3600  # секунд = 60 минут


# ─── Public helpers ───────────────────────────────────────────────────────────


def parse_deep_link(args: str | None) -> int | None:
    """Парсит `newtrigger_<chat_id>` из аргумента /start. Возвращает chat_id или None."""
    if not args or not args.startswith(DEEP_LINK_PREFIX):
        return None
    suffix = args.removeprefix(DEEP_LINK_PREFIX)
    if not suffix:
        return None
    try:
        return int(suffix)
    except ValueError:
        return None


async def _touch_state_ttl(state: FSMContext) -> None:
    """Освежить TTL state-ключа в Valkey.

    RedisStorage обновляет TTL только при `set_state(...)`; `update_data(...)`
    обновляет только data-key TTL. Чтобы оба ключа жили синхронно, на каждом
    действии wizard'а явно «переставляем» текущий state на самого себя.
    """
    current = await state.get_state()
    if current is not None:
        await state.set_state(current)


# ─── TTL refresh middleware ──────────────────────────────────────────────────


@dm_router.message.outer_middleware
@dm_router.callback_query.outer_middleware
async def _ttl_refresh_middleware(
    handler: Callable[..., Any],
    event: Any,
    data: dict[str, Any],
) -> Any:
    """Освежает TTL state-ключа на каждом wizard-действии.

    Если этого не делать, state-key Valkey истечёт через FSM_TTL с момента
    последнего `set_state`, даже если пользователь активен (кликает флаги,
    которые делают только `update_data`).
    """
    state: FSMContext | None = data.get("state")
    if state is not None:
        await _touch_state_ttl(state)
    return await handler(event, data)


# ─── /newtrigger в групповом чате ─────────────────────────────────────────────


async def _can_create_in_chat(
    message: Message,
    db_chat: Chat,
) -> bool:
    """Проверка прав по тем же правилам, что у /add.

    admins_only_add=True → только admin/creator.
    admins_only_add=False → любой is_active-участник.
    """
    if not db_chat.admins_only_add:
        return True
    try:
        member = await message.chat.get_member(message.from_user.id)
    except Exception:
        return False
    return member.status in ("administrator", "creator")


@group_router.message(Command("newtrigger"))
async def newtrigger_group_entry(
    message: Message,
    db_chat: Chat,
    i18n: TranslatorRunner,
) -> None:
    """`/newtrigger` в групповом чате — URL-кнопка с deep-link в ЛС."""
    if not await _can_create_in_chat(message, db_chat):
        await message.answer(i18n.error.no.rights(), parse_mode="HTML")
        return

    me = await message.bot.get_me()
    url = f"https://t.me/{me.username}?start={DEEP_LINK_PREFIX}{message.chat.id}"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=i18n.new.trigger.group.entry.button(), url=url)],
        ],
    )
    await message.answer(
        i18n.new.trigger.group.entry.body(),
        reply_markup=keyboard,
    )
