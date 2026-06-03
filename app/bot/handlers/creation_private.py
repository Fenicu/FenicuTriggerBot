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

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, StateFilter
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from fluentogram import TranslatorRunner
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Chat
from app.db.models.user_chat import UserChat

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


# ─── Deep-link entry: /start newtrigger_<chat_id> ─────────────────────────────


async def _live_check_permission(
    bot: Bot,
    db_chat: Chat,
    user_id: int,
) -> tuple[bool, str | None]:
    """Live-проверка прав через Bot API. Возвращает (ok, причина_отказа_если_не_ok)."""
    if not db_chat or not db_chat.is_active:
        return False, "chat_unavailable"
    try:
        member = await bot.get_chat_member(db_chat.id, user_id)
    except TelegramForbiddenError:
        return False, "bot_forbidden"
    except TelegramBadRequest:
        return False, "chat_unavailable"

    if member.status in ("left", "kicked"):
        return False, "not_a_member"
    is_admin = member.status in ("administrator", "creator")
    if db_chat.admins_only_add and not is_admin:
        return False, "permission_denied"
    return True, None


def _dm_cancel_only_keyboard(i18n: TranslatorRunner) -> InlineKeyboardMarkup:
    """Клава с одной кнопкой Отмена."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=i18n.new.trigger.btn.cancel(),
                callback_data=NewTriggerCB(action="cancel").pack(),
            )],
        ],
    )


async def start_from_deep_link(
    message: Message,
    chat_id: int,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    i18n: TranslatorRunner,
) -> None:
    """Войти в wizard через deep-link `?start=newtrigger_<chat_id>`.

    Делает live get_chat_member; на провал — отказ без входа в state.
    State-conflict guard — placeholder (полная реализация в Task 11).
    """
    # State-guard: если уже есть активный wizard — предлагаем restart/keep.
    current = await state.get_state()
    if current is not None:
        foreign = not current.startswith("NewTriggerStates:")
        body = i18n.new.trigger.conflict.body.foreign() if foreign else i18n.new.trigger.conflict.body()
        await message.answer(body, reply_markup=_conflict_dialog_keyboard(chat_id, i18n))
        return

    db_chat = await session.get(Chat, chat_id)
    if db_chat is None:
        await message.answer(i18n.new.trigger.permission.denied())
        return

    ok, reason = await _live_check_permission(bot, db_chat, message.from_user.id)
    if not ok:
        if reason == "bot_forbidden":
            db_chat.is_active = False
            await session.commit()
        await message.answer(i18n.new.trigger.permission.denied())
        return

    await state.set_state(NewTriggerStates.awaiting_content)
    await state.update_data(chat_id=chat_id, source="deeplink")

    await message.answer(
        i18n.new.trigger.content.prompt(title=db_chat.title or str(chat_id)),
        reply_markup=_dm_cancel_only_keyboard(i18n),
    )


# ─── Conflict-dialog helpers & handlers ──────────────────────────────────────


def _conflict_dialog_keyboard(target_chat_id: int, i18n: TranslatorRunner) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.new.trigger.btn.restart(),
                    callback_data=NewTriggerCB(action="restart", value=str(target_chat_id)).pack(),
                ),
                InlineKeyboardButton(
                    text=i18n.new.trigger.btn.keep(),
                    callback_data=NewTriggerCB(action="keep").pack(),
                ),
            ],
        ],
    )


def _awaiting_content_keyboard(i18n: TranslatorRunner, source: str) -> InlineKeyboardMarkup:
    """Клавиатура для шага awaiting_content. Кнопка 'Сменить чат' только для lobby-flow."""
    rows = []
    if source == "lobby":
        rows.append([InlineKeyboardButton(
            text=i18n.new.trigger.btn.back.to.chat(),
            callback_data=NewTriggerCB(action="back_to_chat").pack(),
        )])
    rows.append([InlineKeyboardButton(
        text=i18n.new.trigger.btn.cancel(),
        callback_data=NewTriggerCB(action="cancel").pack(),
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dm_router.callback_query(StateFilter("*"), NewTriggerCB.filter(F.action == "restart"))
async def handle_conflict_restart(
    callback: CallbackQuery,
    callback_data: NewTriggerCB,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    i18n: TranslatorRunner,
) -> None:
    """Сбросить текущий FSM и начать заново.

    value="0" — restart из lobby (нет target chat'а, идём в choosing_chat) — реализация в Task 12.
    value="<chat_id>" — restart из deep-link (chat предзадан, awaiting_content).
    """
    try:
        chat_id = int(callback_data.value)
    except ValueError:
        await callback.answer()
        return

    await state.clear()

    if chat_id == 0:
        # Lobby-restart: показываем picker.
        chats, total = await _list_eligible_chats(
            session, user_id=callback.from_user.id, page=0,
        )
        if not chats:
            await callback.message.edit_text(i18n.new.trigger.lobby.empty())
            await callback.answer()
            return
        await state.set_state(NewTriggerStates.choosing_chat)
        await state.update_data(source="lobby", page=0)
        await callback.message.edit_text(
            i18n.new.trigger.lobby.title(),
            reply_markup=_chat_picker_keyboard(chats, page=0, total=total, i18n=i18n),
        )
        await callback.answer()
        return

    # Deep-link restart: live-check, потом сразу в awaiting_content.
    db_chat = await session.get(Chat, chat_id)
    if db_chat is None:
        await callback.answer(i18n.new.trigger.permission.denied(), show_alert=True)
        return
    ok, _ = await _live_check_permission(bot, db_chat, callback.from_user.id)
    if not ok:
        await callback.answer(i18n.new.trigger.permission.denied(), show_alert=True)
        return

    await state.set_state(NewTriggerStates.awaiting_content)
    await state.update_data(chat_id=chat_id, source="deeplink")
    await callback.message.edit_text(
        i18n.new.trigger.content.prompt(title=db_chat.title or str(chat_id)),
        reply_markup=_awaiting_content_keyboard(i18n, source="deeplink"),
    )
    await callback.answer()


@dm_router.callback_query(StateFilter("*"), NewTriggerCB.filter(F.action == "keep"))
async def handle_conflict_keep(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: TranslatorRunner,
) -> None:
    """Оставить текущий wizard — просто стираем диалог конфликта."""
    await callback.message.edit_text(i18n.new.trigger.conflict.keep())
    await callback.answer()


# ─── Lobby chat-picker ────────────────────────────────────────────────────────


async def _list_eligible_chats(
    session: AsyncSession,
    user_id: int,
    page: int,
) -> tuple[list[Chat], int]:
    """Чаты, где user может создавать триггеры. Сортировка по chat.updated_at DESC, пагинация."""
    base = (
        select(Chat)
        .join(UserChat, UserChat.chat_id == Chat.id)
        .where(
            UserChat.user_id == user_id,
            UserChat.is_active.is_(True),
            Chat.is_active.is_(True),
            (UserChat.is_admin.is_(True)) | (Chat.admins_only_add.is_(False)),
        )
    )

    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0

    chats = (await session.execute(
        base.order_by(Chat.updated_at.desc())
        .offset(page * CHATS_PER_PAGE)
        .limit(CHATS_PER_PAGE)
    )).scalars().all()

    return list(chats), total


def _truncate(s: str | None, limit: int = 32) -> str:
    if not s:
        return "—"
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _chat_picker_keyboard(
    chats: list[Chat],
    page: int,
    total: int,
    i18n: TranslatorRunner,
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=_truncate(c.title),
            callback_data=NewTriggerCB(action="chat", value=str(c.id)).pack(),
        )]
        for c in chats
    ]
    pages = (total + CHATS_PER_PAGE - 1) // CHATS_PER_PAGE
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(
                text="‹", callback_data=NewTriggerCB(action="page", value=str(page - 1)).pack(),
            ))
        nav.append(InlineKeyboardButton(
            text=i18n.new.trigger.lobby.page.indicator(page=page + 1, total=pages),
            callback_data=NewTriggerCB(action="page", value=str(page)).pack(),
        ))
        if page < pages - 1:
            nav.append(InlineKeyboardButton(
                text="›", callback_data=NewTriggerCB(action="page", value=str(page + 1)).pack(),
            ))
        rows.append(nav)
    rows.append([InlineKeyboardButton(
        text=i18n.new.trigger.btn.cancel(),
        callback_data=NewTriggerCB(action="cancel").pack(),
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@dm_router.message(Command("newtrigger"))
async def newtrigger_dm_entry(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    i18n: TranslatorRunner,
) -> None:
    """`/newtrigger` в ЛС — старт wizard'а с шага choosing_chat.

    При активном state — диалог конфликта (свой или чужой).
    """
    current = await state.get_state()
    if current is not None:
        foreign = not current.startswith("NewTriggerStates:")
        body = i18n.new.trigger.conflict.body.foreign() if foreign else i18n.new.trigger.conflict.body()
        # target_chat_id=0 — спецзначение «после restart показать lobby».
        await message.answer(body, reply_markup=_conflict_dialog_keyboard(0, i18n))
        return

    chats, total = await _list_eligible_chats(session, user_id=message.from_user.id, page=0)
    if not chats:
        await message.answer(i18n.new.trigger.lobby.empty())
        return

    await state.set_state(NewTriggerStates.choosing_chat)
    await state.update_data(source="lobby", page=0)
    await message.answer(
        i18n.new.trigger.lobby.title(),
        reply_markup=_chat_picker_keyboard(chats, page=0, total=total, i18n=i18n),
    )
