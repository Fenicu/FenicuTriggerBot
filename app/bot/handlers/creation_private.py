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

import json
import logging
import re as _re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, StateFilter
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
    Message,
)
from aiogram.types import Message as AiogramMessage
from fluentogram import TranslatorRunner
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.matching import _entities_to_html
from app.core.config import settings
from app.core.valkey import valkey
from app.db.models.chat import Chat
from app.db.models.chat_variable import ChatVariable
from app.db.models.trigger import AccessLevel, MatchType
from app.db.models.user import User
from app.db.models.user_chat import UserChat
from app.services import trigger_service
from app.services.rich_html import (
    RichHtmlError,
    degrade_to_html,
    rich_message_to_html,
    validate_rich_html,
)
from app.services.template_service import get_render_context, render_template, validate_template
from app.services.trigger_service import validate_regex

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
            [
                InlineKeyboardButton(
                    text=i18n.new.trigger.btn.cancel(),
                    callback_data=NewTriggerCB(action="cancel").pack(),
                )
            ],
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
        rows.append(
            [
                InlineKeyboardButton(
                    text=i18n.new.trigger.btn.back.to.chat(),
                    callback_data=NewTriggerCB(action="back_to_chat").pack(),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.new.trigger.btn.cancel(),
                callback_data=NewTriggerCB(action="cancel").pack(),
            )
        ]
    )
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
            session,
            user_id=callback.from_user.id,
            page=0,
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

    chats = (
        (
            await session.execute(
                base.order_by(Chat.updated_at.desc()).offset(page * CHATS_PER_PAGE).limit(CHATS_PER_PAGE)
            )
        )
        .scalars()
        .all()
    )

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
        [
            InlineKeyboardButton(
                text=_truncate(c.title),
                callback_data=NewTriggerCB(action="chat", value=str(c.id)).pack(),
            )
        ]
        for c in chats
    ]
    pages = (total + CHATS_PER_PAGE - 1) // CHATS_PER_PAGE
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(
                InlineKeyboardButton(
                    text="‹",
                    callback_data=NewTriggerCB(action="page", value=str(page - 1)).pack(),
                )
            )
        nav.append(
            InlineKeyboardButton(
                text=i18n.new.trigger.lobby.page.indicator(page=page + 1, total=pages),
                callback_data=NewTriggerCB(action="page", value=str(page)).pack(),
            )
        )
        if page < pages - 1:
            nav.append(
                InlineKeyboardButton(
                    text="›",
                    callback_data=NewTriggerCB(action="page", value=str(page + 1)).pack(),
                )
            )
        rows.append(nav)
    rows.append(
        [
            InlineKeyboardButton(
                text=i18n.new.trigger.btn.cancel(),
                callback_data=NewTriggerCB(action="cancel").pack(),
            )
        ]
    )
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


# ─── Chat-picker callbacks ────────────────────────────────────────────────────


@dm_router.callback_query(
    NewTriggerStates.choosing_chat,
    NewTriggerCB.filter(F.action == "chat"),
)
async def handle_chat_picked(
    callback: CallbackQuery,
    callback_data: NewTriggerCB,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    i18n: TranslatorRunner,
) -> None:
    """Юзер выбрал чат — live re-check, переход в awaiting_content."""
    try:
        chat_id = int(callback_data.value)
    except ValueError:
        await callback.answer()
        return

    db_chat = await session.get(Chat, chat_id)
    if db_chat is None:
        await callback.answer(i18n.new.trigger.permission.denied(), show_alert=True)
        await state.clear()
        return

    ok, reason = await _live_check_permission(bot, db_chat, callback.from_user.id)
    if not ok:
        if reason == "bot_forbidden":
            db_chat.is_active = False
            await session.commit()
        await callback.answer(i18n.new.trigger.permission.denied(), show_alert=True)
        await state.clear()
        return

    await state.set_state(NewTriggerStates.awaiting_content)
    await state.update_data(chat_id=chat_id, source="lobby")
    await callback.message.edit_text(
        i18n.new.trigger.content.prompt(title=db_chat.title or str(chat_id)),
        reply_markup=_awaiting_content_keyboard(i18n, source="lobby"),
    )
    await callback.answer()


@dm_router.callback_query(
    NewTriggerStates.choosing_chat,
    NewTriggerCB.filter(F.action == "page"),
)
async def handle_chat_picker_page(
    callback: CallbackQuery,
    callback_data: NewTriggerCB,
    state: FSMContext,
    session: AsyncSession,
    i18n: TranslatorRunner,
) -> None:
    """Переход на другую страницу chat-picker'а."""
    try:
        page = max(0, int(callback_data.value))
    except ValueError:
        await callback.answer()
        return

    chats, total = await _list_eligible_chats(session, user_id=callback.from_user.id, page=page)
    await state.update_data(page=page)
    await callback.message.edit_reply_markup(
        reply_markup=_chat_picker_keyboard(chats, page=page, total=total, i18n=i18n),
    )
    await callback.answer()


# ─── awaiting_content handler ────────────────────────────────────────────────


@dm_router.message(NewTriggerStates.awaiting_content)
async def handle_content_received(
    message: Message,
    state: FSMContext,
    i18n: TranslatorRunner,
) -> None:
    """Принять контент-сообщение, сохранить dump в state, перейти в awaiting_key.

    Команды-якоря (/cancel, /newtrigger) обрабатываются ДО этого handler'а
    благодаря порядку регистрации (Task 21).

    Если содержимое — команда вида `/foo` или `/cmd arg1 arg2`, показываем
    soft-confirm: «использовать как контент?».
    """
    logger.info(
        "Wizard: content received from user %d (text=%s, caption=%s, sticker=%s, photo=%s)",
        message.from_user.id,
        bool(message.text),
        bool(message.caption),
        bool(message.sticker),
        bool(message.photo),
    )

    # Некопируемые типы (send_copy бросает TypeError): game, paid_media.
    if message.game is not None or message.paid_media is not None:
        await message.answer(i18n.new.trigger.content.wrong.type())
        return

    # rich_message (Bot API 10.1): сериализуем дерево в rich-HTML и сохраняем
    # как rich-триггер. send_copy такой тип не умеет. Форвард — недоверенный
    # вход, поэтому любой сбой сериализации/валидации → честный отказ, не краш.
    if message.rich_message is not None:
        media_base = f"{settings.WEBAPP_URL.rstrip('/')}{settings.URL_PREFIX}{settings.API_V1_STR}"
        try:
            rich_html = rich_message_to_html(message.rich_message, media_base_url=media_base)
            validate_rich_html(rich_html)
        # Широкий catch намеренно: форварднутый rich — недоверенный вход (вкл.
        # RecursionError на глубоком дереве до validate); root cause — через exc_info.
        except Exception as e:
            logger.warning(
                "Wizard: rich serialize failed for user %d: %s",
                message.from_user.id, e, exc_info=True,
            )
            await message.answer(i18n.new.trigger.content.wrong.type())
            return
        await state.update_data(content={"text": rich_html}, rich=True)
        await state.set_state(NewTriggerStates.awaiting_key)
        await message.answer(
            i18n.new.trigger.content.saved() + "\n\n" + i18n.new.trigger.key.prompt(),
            reply_markup=_dm_cancel_only_keyboard(i18n),
        )
        return

    text = (message.text or message.caption or "").strip()
    # Команда — первое слово вида /xxx_yyy (ASCII slug, до 32 символов).
    # Поддерживает и `/cmd`, и `/cmd arg1 arg2`. /cancel и /newtrigger сюда
    # не доедут — их перехватит Command-фильтр выше по router'у.
    first_token = text.split(maxsplit=1)[0] if text else ""
    is_command_like = bool(_re.match(r"^/[a-zA-Z][a-zA-Z0-9_]{0,31}(@\w+)?$", first_token))

    if is_command_like:
        content = json.loads(message.model_dump_json(exclude_unset=True, exclude_defaults=True))
        await state.update_data(pending_content=content)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=i18n.new.trigger.btn.use.this(),
                        callback_data=NewTriggerCB(action="confirm_content").pack(),
                    ),
                    InlineKeyboardButton(
                        text=i18n.new.trigger.btn.send.another(),
                        callback_data=NewTriggerCB(action="reject_content").pack(),
                    ),
                ],
            ]
        )
        await message.answer(i18n.new.trigger.content.command.warning(), reply_markup=kb)
        return

    content = json.loads(message.model_dump_json(exclude_unset=True, exclude_defaults=True))
    await state.update_data(content=content, rich=False)
    await state.set_state(NewTriggerStates.awaiting_key)
    await message.answer(
        i18n.new.trigger.content.saved() + "\n\n" + i18n.new.trigger.key.prompt(),
        reply_markup=_dm_cancel_only_keyboard(i18n),
    )


@dm_router.callback_query(
    NewTriggerStates.awaiting_content,
    NewTriggerCB.filter(F.action == "confirm_content"),
)
async def handle_confirm_command_content(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: TranslatorRunner,
) -> None:
    data = await state.get_data()
    pending = data.get("pending_content")
    if not pending:
        await callback.answer()
        return
    await state.update_data(content=pending, pending_content=None, rich=False)
    await state.set_state(NewTriggerStates.awaiting_key)
    await callback.message.edit_text(
        i18n.new.trigger.content.saved() + "\n\n" + i18n.new.trigger.key.prompt(),
        reply_markup=_dm_cancel_only_keyboard(i18n),
    )
    await callback.answer()


@dm_router.callback_query(
    NewTriggerStates.awaiting_content,
    NewTriggerCB.filter(F.action == "reject_content"),
)
async def handle_reject_command_content(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: TranslatorRunner,
) -> None:
    await state.update_data(pending_content=None)
    data = await state.get_data()
    chat_id = data.get("chat_id")
    source = data.get("source", "lobby")
    title = str(chat_id) if chat_id else ""
    await callback.message.edit_text(
        i18n.new.trigger.content.prompt(title=title),
        reply_markup=_awaiting_content_keyboard(i18n, source=source),
    )
    await callback.answer()


@dm_router.callback_query(
    NewTriggerStates.awaiting_content,
    NewTriggerCB.filter(F.action == "back_to_chat"),
)
async def handle_back_to_chat(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    i18n: TranslatorRunner,
) -> None:
    data = await state.get_data()
    if data.get("source") != "lobby":
        await callback.answer()
        return

    chats, total = await _list_eligible_chats(
        session,
        user_id=callback.from_user.id,
        page=0,
    )
    await state.set_state(NewTriggerStates.choosing_chat)
    await state.update_data(page=0)
    await callback.message.edit_text(
        i18n.new.trigger.lobby.title(),
        reply_markup=_chat_picker_keyboard(chats, page=0, total=total, i18n=i18n),
    )
    await callback.answer()


# ─── awaiting_key handler ────────────────────────────────────────────────────

# Лимит длины ключа для UX-валидации в wizard'е.
# Модель Trigger.key_phrase = Text (без БД-лимита). 256 — продуктовое решение:
# - regex уже ограничен в validate_regex до 500 символов;
# - для exact/contains 256 — практический предел осмысленного ключа;
# - превышение → ранний отказ до похода в trigger_service.create_trigger.
KEY_PHRASE_LIMIT = 256


@dm_router.message(NewTriggerStates.awaiting_key, F.text)
async def handle_key_received(
    message: Message,
    state: FSMContext,
    i18n: TranslatorRunner,
) -> None:
    logger.info("Wizard: key received from user %d (len=%d)", message.from_user.id, len(message.text or ""))
    text = (message.text or "").strip()
    if not text:
        await message.answer(i18n.new.trigger.key.empty())
        return
    if len(text) > KEY_PHRASE_LIMIT:
        await message.answer(i18n.new.trigger.key.too.long(limit=KEY_PHRASE_LIMIT))
        return

    await state.update_data(
        key_phrase=text,
        match_type="exact",
        is_case_sensitive=False,
        access_level="all",
        is_template=False,
    )
    logger.info("Wizard: key data saved, about to set_state(configuring_flags)")
    await state.set_state(NewTriggerStates.configuring_flags)
    logger.info("Wizard: state set, calling _render_flags_message")
    try:
        await _render_flags_message(message, state, i18n)
    except Exception:
        logger.exception("Wizard: handle_key_received: _render_flags_message raised")
        raise
    logger.info("Wizard: _render_flags_message returned cleanly")


def _flags_keyboard(
    data: dict,
    i18n: TranslatorRunner,
) -> InlineKeyboardMarkup:
    match = data.get("match_type", "exact")  # exact/contains/regexp
    case_on = data.get("is_case_sensitive", False)
    access = data.get("access_level", "all")
    template = data.get("is_template", False)

    def radio(label: str, selected: bool) -> str:
        return f"• {label}" if selected else f"◦ {label}"

    rows = [
        [
            InlineKeyboardButton(
                text=radio(i18n.new.trigger.flags.match.exact(), match == "exact"),
                callback_data=NewTriggerCB(action="flag", value="match|exact").pack(),
            ),
            InlineKeyboardButton(
                text=radio(i18n.new.trigger.flags.match.contains(), match == "contains"),
                callback_data=NewTriggerCB(action="flag", value="match|contains").pack(),
            ),
            InlineKeyboardButton(
                text=radio(i18n.new.trigger.flags.match.regex(), match == "regexp"),
                callback_data=NewTriggerCB(action="flag", value="match|regexp").pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=radio(i18n.new.trigger.flags.case.on(), case_on),
                callback_data=NewTriggerCB(action="flag", value="case").pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=radio(i18n.new.trigger.flags.access.all(), access == "all"),
                callback_data=NewTriggerCB(action="flag", value="access|all").pack(),
            ),
            InlineKeyboardButton(
                text=radio(i18n.new.trigger.flags.access.admins(), access == "admins"),
                callback_data=NewTriggerCB(action="flag", value="access|admins").pack(),
            ),
            InlineKeyboardButton(
                text=radio(i18n.new.trigger.flags.access.owner(), access == "owner"),
                callback_data=NewTriggerCB(action="flag", value="access|owner").pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=radio(i18n.new.trigger.flags.template(), template),
                callback_data=NewTriggerCB(action="flag", value="template").pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=i18n.new.trigger.btn.next(),
                callback_data=NewTriggerCB(action="next").pack(),
            ),
        ],
        [
            InlineKeyboardButton(
                text=i18n.new.trigger.btn.back.to.key(),
                callback_data=NewTriggerCB(action="back_to_key").pack(),
            ),
            InlineKeyboardButton(
                text=i18n.new.trigger.btn.cancel(),
                callback_data=NewTriggerCB(action="cancel").pack(),
            ),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_flags_message(
    target: Message | CallbackQuery,
    state: FSMContext,
    i18n: TranslatorRunner,
) -> None:
    """Перерисовать сообщение с клавиатурой флагов.

    target — Message (после handle_key_received: шлём новое) или
    CallbackQuery (после флага/back_to_flags: редактируем родительское).
    """
    logger.info("Wizard: _render_flags_message START target=%s", type(target).__name__)
    try:
        data = await state.get_data()
        logger.info("Wizard: got state data, keys=%s", list(data.keys()))
        text = i18n.new.trigger.flags.title(phrase=data.get("key_phrase", ""))
        logger.info("Wizard: rendered title text len=%d preview=%r", len(text), text[:80])
        keyboard = _flags_keyboard(data, i18n)
        logger.info("Wizard: keyboard built, rows=%d", len(keyboard.inline_keyboard))
        if isinstance(target, CallbackQuery):
            logger.info("Wizard: editing callback.message")
            await target.message.edit_text(text, reply_markup=keyboard)
        else:
            logger.info("Wizard: answering new message")
            await target.answer(text, reply_markup=keyboard)
        logger.info("Wizard: render flags message DONE")
    except Exception:
        logger.exception("Wizard: _render_flags_message EXPLODED")
        raise


@dm_router.callback_query(
    NewTriggerStates.configuring_flags,
    NewTriggerCB.filter(F.action == "flag"),
)
async def handle_flag_toggle(
    callback: CallbackQuery,
    callback_data: NewTriggerCB,
    state: FSMContext,
    i18n: TranslatorRunner,
) -> None:
    logger.info("Wizard: flag toggle from user %d value=%r", callback.from_user.id, callback_data.value)
    data = await state.get_data()
    value = callback_data.value

    if value.startswith("match|"):
        new_match = value.split("|", 1)[1]
        if new_match in ("exact", "contains", "regexp"):
            await state.update_data(match_type=new_match)
    elif value == "case":
        await state.update_data(is_case_sensitive=not data.get("is_case_sensitive", False))
    elif value.startswith("access|"):
        new_access = value.split("|", 1)[1]
        if new_access in ("all", "admins", "owner"):
            await state.update_data(access_level=new_access)
    elif value == "template":
        await state.update_data(is_template=not data.get("is_template", False))
    else:
        await callback.answer()
        return

    await _render_flags_message(callback, state, i18n)
    await callback.answer()


# ─── configuring_flags → confirming ─────────────────────────────────────────


@dm_router.callback_query(
    NewTriggerStates.configuring_flags,
    NewTriggerCB.filter(F.action == "next"),
)
async def handle_next(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    i18n: TranslatorRunner,
) -> None:
    """Переход configuring_flags → confirming с валидацией regex/template."""
    logger.info("Wizard: next from user %d", callback.from_user.id)
    data = await state.get_data()

    if data.get("match_type") == "regexp":
        err = await validate_regex(data.get("key_phrase", ""))
        if err:
            await callback.answer(
                i18n.new.trigger.flags.regex.invalid(error=err),
                show_alert=True,
            )
            return

    if data.get("is_template"):
        content = data.get("content") or {}
        text_or_caption = content.get("text") or content.get("caption") or ""
        try:
            validate_template(text_or_caption)
        except Exception as e:
            await callback.answer(
                i18n.new.trigger.flags.template.invalid(error=str(e)),
                show_alert=True,
            )
            return

    await state.set_state(NewTriggerStates.confirming)
    await _render_preview(callback, state, session, bot, i18n)
    await callback.answer()


def _confirming_keyboard(i18n: TranslatorRunner) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.new.trigger.btn.save(),
                    callback_data=NewTriggerCB(action="save").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.new.trigger.btn.back.to.flags(),
                    callback_data=NewTriggerCB(action="back_to_flags").pack(),
                ),
                InlineKeyboardButton(
                    text=i18n.new.trigger.btn.cancel(),
                    callback_data=NewTriggerCB(action="cancel").pack(),
                ),
            ],
        ],
    )


class _PreviewChat:
    """Минимальный stub чата-цели для get_render_context."""

    def __init__(self, chat_id: int, title: str | None) -> None:
        self.id = chat_id
        self.title = title


async def _render_preview(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    i18n: TranslatorRunner,
) -> None:
    """Послать send_copy контента + управляющее сообщение с summary.

    Для template-триггеров рендер с MIXED context: user.* — от инициатора,
    chat.*/vars.*/timezone — от целевого чата (по chat_id из state).
    """
    data = await state.get_data()
    content = dict(data.get("content") or {})  # copy
    chat_id = data["chat_id"]
    is_template = data.get("is_template", False)
    is_rich = data.get("rich", False)

    db_chat = await session.get(Chat, chat_id)
    chat_title = db_chat.title if db_chat else str(chat_id)

    entities_html_ok = True

    # rich-контент в matching всегда идёт через render_rich_template, не через
    # plain-template-рендер. Прогон rich-HTML через _entities_to_html+render_template
    # исказил бы его, поэтому plain-template-ветку защищаем от rich.
    if is_template and not is_rich:
        # vars/timezone — из целевого чата
        vars_stmt = select(ChatVariable).where(ChatVariable.chat_id == chat_id)
        chat_vars = {v.key: v.value for v in (await session.execute(vars_stmt)).scalars()}

        fake_chat = _PreviewChat(chat_id, chat_title)
        ctx = get_render_context(
            user=callback.from_user,
            chat=fake_chat,
            variables=chat_vars,
            timezone=getattr(db_chat, "timezone", None) if db_chat else None,
        )

        text_entities = content.pop("entities", None)
        caption_entities = content.pop("caption_entities", None)
        if content.get("text"):
            try:
                html_text = _entities_to_html(content["text"], text_entities)
            except Exception:
                logger.warning("Preview: _entities_to_html failed for text", exc_info=True)
                entities_html_ok = False
                html_text = content["text"]
            try:
                content["text"] = render_template(html_text, ctx)
            except Exception:
                content["text"] = html_text
        if content.get("caption"):
            try:
                html_caption = _entities_to_html(content["caption"], caption_entities)
            except Exception:
                logger.warning("Preview: _entities_to_html failed for caption", exc_info=True)
                entities_html_ok = False
                html_caption = content["caption"]
            try:
                content["caption"] = render_template(html_caption, ctx)
            except Exception:
                content["caption"] = html_caption

    # отправка превью в DM
    if is_rich:
        rich_html = content.get("text") or ""
        try:
            validate_rich_html(rich_html)
            await bot.send_rich_message(
                chat_id=callback.message.chat.id,
                rich_message=InputRichMessage(html=rich_html),
            )
        except TelegramRetryAfter as e:
            await callback.answer(
                i18n.new.trigger.send.copy.retry.after(seconds=e.retry_after),
                show_alert=True,
            )
            return
        except (TelegramBadRequest, RichHtmlError) as e:
            logger.warning("Wizard preview send_rich failed: %s; degrading", e)
            try:
                await bot.send_message(
                    callback.message.chat.id, degrade_to_html(rich_html), parse_mode="HTML"
                )
            except (TelegramBadRequest, TelegramRetryAfter):
                await state.update_data(content=None, rich=False)
                await state.set_state(NewTriggerStates.awaiting_content)
                await callback.message.edit_text(i18n.new.trigger.send.copy.failed())
                await callback.answer()
                return
    else:
        try:
            saved = AiogramMessage.model_validate(content)
            saved._bot = bot
            await saved.send_copy(
                chat_id=callback.message.chat.id,
                parse_mode="HTML" if is_template else None,
            )
        except TelegramRetryAfter as e:
            await callback.answer(
                i18n.new.trigger.send.copy.retry.after(seconds=e.retry_after),
                show_alert=True,
            )
            return
        except (TelegramBadRequest, TypeError) as e:
            logger.warning("Wizard preview send_copy failed: %s", e)
            await state.update_data(content=None, rich=False)
            await state.set_state(NewTriggerStates.awaiting_content)
            await callback.message.edit_text(i18n.new.trigger.send.copy.failed())
            await callback.answer()
            return

    # Управляющее сообщение
    match_label = {
        "exact": i18n.new.trigger.flags.match.exact(),
        "contains": i18n.new.trigger.flags.match.contains(),
        "regexp": i18n.new.trigger.flags.match.regex(),
    }.get(data.get("match_type", "exact"), "?")
    case_label = "case-sensitive" if data.get("is_case_sensitive") else "case-insensitive"
    access_label = {
        "all": i18n.new.trigger.flags.access.all(),
        "admins": i18n.new.trigger.flags.access.admins(),
        "owner": i18n.new.trigger.flags.access.owner(),
    }.get(data.get("access_level", "all"), "?")
    tmpl_label = "on" if data.get("is_template") else "off"

    summary = i18n.new.trigger.confirm.summary(
        phrase=data.get("key_phrase", ""),
        match_type=match_label,
        case_mode=case_label,
        access=access_label,
        template=tmpl_label,
        chat_title=chat_title,
    )
    if not entities_html_ok:
        summary += "\n\n" + i18n.new.trigger.preview.entities.warning()

    # Отдельным сообщением, чтобы preview и summary не схлопнулись
    await bot.send_message(
        chat_id=callback.message.chat.id,
        text=summary,
        reply_markup=_confirming_keyboard(i18n),
    )


@dm_router.callback_query(
    NewTriggerStates.configuring_flags,
    NewTriggerCB.filter(F.action == "back_to_key"),
)
async def handle_back_to_key(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: TranslatorRunner,
) -> None:
    """Возврат в awaiting_key."""
    await state.set_state(NewTriggerStates.awaiting_key)
    await callback.message.edit_text(
        i18n.new.trigger.key.prompt(),
        reply_markup=_dm_cancel_only_keyboard(i18n),
    )
    await callback.answer()


# ─── _save_via_wizard ─────────────────────────────────────────────────────────


@dataclass
class SaveResult:
    status: str  # "ok" | "lock_busy" | "permission_lost" | "chat_unavailable" | "db_error"
    trigger_id: int | None = None
    skip_moderation: bool = False
    error: str | None = None


# Lua compare-and-delete: удалить ключ только если value совпадает.
# Защищает от race'а, когда TTL истёк и параллельный SETNX взял ключ заново —
# наш delete не должен удалить чужой лок.
_LUA_RELEASE_LOCK = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


async def _save_via_wizard(
    *,
    user_id: int,
    chat_id: int,
    content: dict,
    key_phrase: str,
    match_type: str,
    is_case_sensitive: bool,
    access_level: str,
    is_template: bool,
    rich: bool = False,
    session: AsyncSession,
    bot: Bot,
) -> SaveResult:
    """Сохранить триггер с защитой от concurrent save и финальной re-проверкой прав.

    Лок: `nt:save_lock:<user_id>` через SETNX с TTL SAVE_LOCK_TTL.
    Освобождение лока — Lua compare-and-delete по uuid owner-token.
    """
    lock_key = f"nt:save_lock:{user_id}"
    # Уникальный owner-token, чтобы при истечении TTL не удалить чужой лок.
    lock_token = uuid.uuid4().hex
    locked = await valkey.set(lock_key, lock_token, nx=True, ex=SAVE_LOCK_TTL)
    if not locked:
        return SaveResult(status="lock_busy")

    try:
        db_chat = await session.get(Chat, chat_id)
        ok, reason = await _live_check_permission(bot, db_chat, user_id) if db_chat else (False, "chat_unavailable")
        if not ok:
            if reason == "bot_forbidden" and db_chat:
                db_chat.is_active = False
                await session.commit()
            return SaveResult(
                status="permission_lost" if reason == "permission_denied" else "chat_unavailable",
            )

        # Модерация — те же правила что у /add
        db_user = await session.get(User, user_id)
        skip_moderation = bool(
            getattr(db_chat, "is_trusted", False)
            or (db_user and (db_user.is_trusted or db_user.is_bot_moderator))
            or user_id in settings.BOT_ADMINS
        )

        try:
            trigger = await trigger_service.create_trigger(
                session=session,
                chat_id=chat_id,
                key_phrase=key_phrase,
                content=content,
                match_type=MatchType(match_type),
                is_case_sensitive=is_case_sensitive,
                access_level=AccessLevel(access_level),
                created_by=user_id,
                skip_moderation=skip_moderation,
                is_template=is_template,
                rich=rich,
            )
        except Exception as e:
            logger.exception("Wizard: create_trigger failed for user %d", user_id)
            return SaveResult(status="db_error", error=str(e))
        return SaveResult(status="ok", trigger_id=trigger.id, skip_moderation=skip_moderation)
    finally:
        # compare-and-delete: удаляем только если ключ всё ещё наш.
        try:
            await valkey.eval(_LUA_RELEASE_LOCK, 1, lock_key, lock_token)
        except Exception:
            logger.warning("Wizard: failed to release save lock %s", lock_key, exc_info=True)


# ─── Callbacks: save / again / finish / back_to_flags ────────────────────────


def _after_save_keyboard(i18n: TranslatorRunner) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=i18n.new.trigger.btn.again(),
                    callback_data=NewTriggerCB(action="again").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text=i18n.new.trigger.btn.finish(),
                    callback_data=NewTriggerCB(action="finish").pack(),
                )
            ],
        ],
    )


@dm_router.callback_query(
    NewTriggerStates.confirming,
    NewTriggerCB.filter(F.action == "save"),
)
async def handle_save(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    bot: Bot,
    i18n: TranslatorRunner,
) -> None:
    logger.info("Wizard: save from user %d", callback.from_user.id)
    data = await state.get_data()
    result = await _save_via_wizard(
        user_id=callback.from_user.id,
        chat_id=data["chat_id"],
        content=data["content"],
        key_phrase=data["key_phrase"],
        match_type=data["match_type"],
        is_case_sensitive=data["is_case_sensitive"],
        access_level=data["access_level"],
        is_template=data["is_template"],
        rich=data.get("rich", False),
        session=session,
        bot=bot,
    )

    if result.status == "lock_busy":
        await callback.answer(i18n.new.trigger.save.busy(), show_alert=True)
        return
    if result.status == "permission_lost":
        await callback.message.edit_text(i18n.new.trigger.permission.lost())
        await state.clear()
        await callback.answer()
        return
    if result.status == "chat_unavailable":
        await callback.message.edit_text(i18n.new.trigger.permission.denied())
        await state.clear()
        await callback.answer()
        return
    if result.status == "db_error":
        # Триггер не сохранён — возвращаем в configuring_flags и перерисовываем
        # клавиатуру, иначе старая Save/back/Cancel клава из confirming будет
        # сматчиваться неверно с новым state'ом.
        await state.set_state(NewTriggerStates.configuring_flags)
        await callback.answer(
            i18n.new.trigger.create.failed(error=(result.error or "?")[:200]),
            show_alert=True,
        )
        await _render_flags_message(callback, state, i18n)
        return

    text = i18n.new.trigger.confirm.created()
    if not result.skip_moderation:
        text += "\n\n" + i18n.new.trigger.confirm.moderation.pending()
    await callback.message.edit_text(text, reply_markup=_after_save_keyboard(i18n))
    await state.clear()
    # chat_id для возможного again — сохраним заново
    await state.update_data(chat_id=data["chat_id"], source=data.get("source", "lobby"))
    await callback.answer()


@dm_router.callback_query(NewTriggerCB.filter(F.action == "again"))
async def handle_again(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: TranslatorRunner,
) -> None:
    data = await state.get_data()
    chat_id = data.get("chat_id")
    source = data.get("source", "lobby")
    if chat_id is None:
        await callback.answer()
        return
    await state.set_state(NewTriggerStates.awaiting_content)
    await state.update_data(
        chat_id=chat_id,
        source=source,
        content=None,
        key_phrase=None,
        match_type="exact",
        is_case_sensitive=False,
        access_level="all",
        is_template=False,
        rich=False,
    )
    await callback.message.edit_text(
        i18n.new.trigger.content.prompt(title=str(chat_id)),
        reply_markup=_awaiting_content_keyboard(i18n, source=source),
    )
    await callback.answer()


@dm_router.callback_query(NewTriggerCB.filter(F.action == "finish"))
async def handle_finish(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: TranslatorRunner,
) -> None:
    await state.clear()
    await callback.message.edit_text(i18n.new.trigger.cancel.done())
    await callback.answer()


@dm_router.callback_query(
    NewTriggerStates.confirming,
    NewTriggerCB.filter(F.action == "back_to_flags"),
)
async def handle_back_to_flags(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: TranslatorRunner,
) -> None:
    await state.set_state(NewTriggerStates.configuring_flags)
    await _render_flags_message(callback, state, i18n)
    await callback.answer()


# ─── /cancel command + nt:cancel callback ────────────────────────────────────


@dm_router.message(StateFilter("*"), Command("cancel"))
async def handle_cancel_command(
    message: Message,
    state: FSMContext,
    i18n: TranslatorRunner,
) -> None:
    """`/cancel` чистит state ТОЛЬКО если он — наш wizard. Чужой FSM не трогаем."""
    current = await state.get_state()
    if current is None:
        return  # нет активной сессии — игнорируем
    if not current.startswith("NewTriggerStates:"):
        return  # чужой FSM — не трогаем
    await state.clear()
    await message.answer(i18n.new.trigger.cancel.done())


@dm_router.callback_query(StateFilter("*"), NewTriggerCB.filter(F.action == "cancel"))
async def handle_cancel_callback(
    callback: CallbackQuery,
    state: FSMContext,
    i18n: TranslatorRunner,
) -> None:
    current = await state.get_state()
    if current is None:
        await callback.answer()
        return
    if not current.startswith("NewTriggerStates:"):
        await callback.answer()
        return
    await state.clear()
    await callback.message.edit_text(i18n.new.trigger.cancel.done())
    await callback.answer()


# ─── Catch-all для stale callback'ов и wrong-type fallthrough ─────────────────


@dm_router.callback_query(NewTriggerCB.filter())
async def handle_stale_callback(
    callback: CallbackQuery,
    callback_data: NewTriggerCB,
    state: FSMContext,
    i18n: TranslatorRunner,
) -> None:
    """Catch-all для wizard-callback'ов, не попавших ни под один state-bound handler.

    Сценарии:
    - Клик по кнопке из старого сообщения после state.clear() → session expired.
    - Клик по 'wrong-step' кнопке (например save из awaiting_content) → silent ack.
    """
    current = await state.get_state()
    if current is None:
        await callback.answer(i18n.new.trigger.session.expired(), show_alert=True)
        return
    await callback.answer()


# Message-fallthrough: только когда state — наш wizard. Иначе пропускаем
# в другие router'ы (admin/welcome/etc), чтобы их command-handler'ы получили
# свои /admin, /lang и т.д.
_WIZARD_STATES = StateFilter(
    NewTriggerStates.choosing_chat,
    NewTriggerStates.awaiting_content,
    NewTriggerStates.awaiting_key,
    NewTriggerStates.configuring_flags,
    NewTriggerStates.confirming,
)


@dm_router.message(_WIZARD_STATES)
async def handle_dm_fallthrough(
    message: Message,
    state: FSMContext,
    i18n: TranslatorRunner,
) -> None:
    """Сообщение пришло в wizard-state, но не подошло ни под один state-bound
    message-handler (например, в `awaiting_key` пришло фото).

    Делаем мягкое напоминание по текущему шагу. Сообщения вне wizard-states
    (включая state=None и чужие state'ы вроде SettingsStates) НЕ перехватываются —
    у aiogram срабатывает следующий router в очереди.
    """
    current = await state.get_state()
    if current == NewTriggerStates.awaiting_content.state:
        await message.answer(i18n.new.trigger.content.wrong.type())
    elif current == NewTriggerStates.awaiting_key.state:
        await message.answer(i18n.new.trigger.key.wrong.type())
    elif current in (
        NewTriggerStates.configuring_flags.state,
        NewTriggerStates.confirming.state,
        NewTriggerStates.choosing_chat.state,
    ):
        await message.answer(i18n.new.trigger.flags.wrong.input())
