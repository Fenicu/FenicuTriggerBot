"""Интеграционные тесты wizard'а через реальный aiogram Dispatcher с MockedSession.

Эти тесты гоняют updates через настоящий `Dispatcher.feed_raw_update(bot, update)` —
со всеми state-filter'ами, middleware'ами и order'ом регистрации. Они ловят баги,
которые прямые вызовы handler-функций пропускают: incorrect filter, edit чужого
сообщения, callback не достигший своего handler'а из-за state-mismatch.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import BaseEventIsolation, StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.strategy import FSMStrategy
from aiogram.types import BotCommand
from aiogram.dispatcher.middlewares.base import BaseMiddleware

from app.bot.handlers.creation_private import (
    NewTriggerStates,
    dm_router,
)

from tests.handlers._mocked_bot import (
    MockedSession,
    build_update_callback,
    build_update_message,
)


class _FakeI18nNode:
    """Dotted-path i18n stub без MagicMock-magic-attr хаков."""

    def __init__(self, path: str = "") -> None:
        object.__setattr__(self, "_path", path)

    def __getattr__(self, name: str) -> "_FakeI18nNode":
        return _FakeI18nNode(f"{self._path}.{name}" if self._path else name)

    def __call__(self, **kwargs: Any) -> str:
        if kwargs:
            args = ",".join(f"{k}={v}" for k, v in kwargs.items())
            return f"{self._path}({args})"
        return self._path or ""


class _InjectMiddleware(BaseMiddleware):
    """Минимальная middleware, инжектящая i18n и (опционально) session/db_chat/db_user."""

    def __init__(
        self,
        *,
        i18n: _FakeI18nNode,
        session: Any = None,
        db_chat: Any = None,
        db_user: Any = None,
    ) -> None:
        self.i18n = i18n
        self.session = session
        self.db_chat = db_chat
        self.db_user = db_user

    async def __call__(self, handler, event, data):
        data["i18n"] = self.i18n
        if self.session is not None:
            data["session"] = self.session
        if self.db_chat is not None:
            data["db_chat"] = self.db_chat
        if self.db_user is not None:
            data["db_user"] = self.db_user
        return await handler(event, data)


@pytest.fixture
def mocked_session() -> MockedSession:
    return MockedSession()


@pytest.fixture
def bot(mocked_session: MockedSession) -> Bot:
    return Bot(token="123456:test-token-fake", session=mocked_session)


@pytest.fixture
def storage() -> MemoryStorage:
    return MemoryStorage()


@pytest.fixture
def dispatcher(storage: MemoryStorage) -> Dispatcher:
    # Router — глобальный singleton; отвязываем от прошлого диспатчера через protected attr.
    dm_router._parent_router = None
    dp = Dispatcher(storage=storage, fsm_strategy=FSMStrategy.USER_IN_CHAT)
    dp.include_router(dm_router)
    return dp


@pytest.fixture
def i18n() -> _FakeI18nNode:
    return _FakeI18nNode()


@pytest.fixture
def inject_middleware(
    i18n: _FakeI18nNode,
    db_session,
) -> _InjectMiddleware:
    return _InjectMiddleware(i18n=i18n, session=db_session)


@pytest.fixture
def dispatcher_with_inject(
    dispatcher: Dispatcher, inject_middleware: _InjectMiddleware
) -> Dispatcher:
    dispatcher.update.outer_middleware(inject_middleware)
    return dispatcher


async def _set_state_directly(
    storage: MemoryStorage,
    *,
    bot: Bot,
    chat_id: int,
    user_id: int,
    state: str,
    data: dict | None = None,
) -> None:
    """Прямо записать state и data в MemoryStorage, минуя dispatcher."""
    key = StorageKey(bot_id=bot.id, chat_id=chat_id, user_id=user_id)
    await storage.set_state(key, state)
    if data:
        await storage.set_data(key, data)


# ─── Тесты: ключевая регрессия ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_key_received_responds_with_new_message_not_edit(
    dispatcher_with_inject: Dispatcher,
    bot: Bot,
    mocked_session: MockedSession,
    storage: MemoryStorage,
) -> None:
    """РЕГРЕССИЯ: после ввода ключа бот должен отправить НОВОЕ сообщение с клавой флагов
    (через `sendMessage`), а не пытаться `editMessageText` чужого сообщения юзера."""
    user_id, chat_id = 42, 42
    target_chat_id = -1001234567890

    await _set_state_directly(
        storage,
        bot=bot,
        chat_id=chat_id,
        user_id=user_id,
        state=NewTriggerStates.awaiting_key.state,
        data={"chat_id": target_chat_id, "source": "lobby"},
    )

    update = build_update_message(
        update_id=10, message_id=100, chat_id=chat_id, user_id=user_id, text="привет"
    )
    await dispatcher_with_inject.feed_raw_update(bot, update)

    method_names = mocked_session.method_names()

    assert "SendMessage" in method_names, (
        f"Ожидался SendMessage с клавой флагов, но Bot API не дернулся. "
        f"Calls: {method_names}"
    )
    assert "EditMessageText" not in method_names, (
        "Бот пытался отредактировать сообщение (вероятно — юзера, что Telegram "
        "запретит). Должен был отправить новое."
    )

    # Один из SendMessage должен содержать клавиатуру с кнопкой Next
    send_msgs = mocked_session.payloads_for("SendMessage")
    has_flags_kb = any(
        m.get("reply_markup") and any(
            btn.get("callback_data", "").startswith("nt:next")
            for row in m["reply_markup"].get("inline_keyboard", [])
            for btn in row
        )
        for m in send_msgs
    )
    assert has_flags_kb, f"Ни в одном SendMessage нет клавы с 'nt:next'. Payloads: {send_msgs}"


@pytest.mark.asyncio
async def test_flag_toggle_edits_existing_bot_message(
    dispatcher_with_inject: Dispatcher,
    bot: Bot,
    mocked_session: MockedSession,
    storage: MemoryStorage,
) -> None:
    """Клик по кнопке флага должен ОТРЕДАКТИРОВАТЬ то же сообщение (callback.message),
    а не слать новое — это сообщение принадлежит боту, edit разрешён."""
    user_id, chat_id = 42, 42
    target_chat_id = -1001234567890

    await _set_state_directly(
        storage,
        bot=bot,
        chat_id=chat_id,
        user_id=user_id,
        state=NewTriggerStates.configuring_flags.state,
        data={
            "chat_id": target_chat_id, "source": "lobby",
            "key_phrase": "привет", "match_type": "exact",
            "is_case_sensitive": False, "access_level": "all", "is_template": False,
        },
    )

    update = build_update_callback(
        update_id=20, cb_id="cb1", chat_id=chat_id, user_id=user_id,
        data="nt:flag:match|contains",
    )
    await dispatcher_with_inject.feed_raw_update(bot, update)

    method_names = mocked_session.method_names()
    assert "EditMessageText" in method_names, (
        f"Клик по флагу должен редактировать сообщение бота. Calls: {method_names}"
    )
    assert "AnswerCallbackQuery" in method_names


@pytest.mark.asyncio
async def test_next_in_configuring_flags_advances_to_confirming(
    dispatcher_with_inject: Dispatcher,
    bot: Bot,
    mocked_session: MockedSession,
    storage: MemoryStorage,
    db_session,
) -> None:
    """Клик 'Далее' валидирует и переходит в confirming → шлёт preview через
    send_copy (т.е. CopyMessage) + summary через SendMessage."""
    from tests.factories import create_chat, create_user
    user = await create_user(db_session)
    chat = await create_chat(db_session, admins_only_add=False, title="Target")

    user_id, chat_id = user.id, user.id

    await _set_state_directly(
        storage,
        bot=bot,
        chat_id=chat_id,
        user_id=user_id,
        state=NewTriggerStates.configuring_flags.state,
        data={
            "chat_id": chat.id, "source": "lobby",
            "content": {
                "message_id": 1, "date": 0,
                "chat": {"id": chat.id, "type": "supergroup", "title": "T"},
                "text": "Hello",
            },
            "key_phrase": "привет", "match_type": "exact",
            "is_case_sensitive": False, "access_level": "all", "is_template": False,
        },
    )

    update = build_update_callback(
        update_id=30, cb_id="cb2", chat_id=chat_id, user_id=user_id, data="nt:next:",
    )
    await dispatcher_with_inject.feed_raw_update(bot, update)

    names = mocked_session.method_names()
    # Preview: для text-контента это CopyMessage; для template и других вариантов
    # тоже не EditMessageText юзера.
    assert any(n in ("CopyMessage", "SendMessage") for n in names), (
        f"Preview должен сгенерировать API-вызов. Calls: {names}"
    )
    assert "AnswerCallbackQuery" in names

    # state теперь confirming
    key = StorageKey(bot_id=bot.id, chat_id=chat_id, user_id=user_id)
    cur_state = await storage.get_state(key)
    assert cur_state == NewTriggerStates.confirming.state


@pytest.mark.asyncio
async def test_back_to_flags_from_confirming_re_renders_keyboard(
    dispatcher_with_inject: Dispatcher,
    bot: Bot,
    mocked_session: MockedSession,
    storage: MemoryStorage,
) -> None:
    """Кнопка 'Изменить параметры' в confirming должна вернуть в configuring_flags
    и перерисовать клавиатуру флагов через editMessageText (на сообщении бота)."""
    user_id, chat_id = 42, 42

    await _set_state_directly(
        storage,
        bot=bot,
        chat_id=chat_id,
        user_id=user_id,
        state=NewTriggerStates.confirming.state,
        data={
            "chat_id": -1, "source": "lobby",
            "key_phrase": "привет", "match_type": "exact",
            "is_case_sensitive": False, "access_level": "all", "is_template": False,
        },
    )

    update = build_update_callback(
        update_id=40, cb_id="cb3", chat_id=chat_id, user_id=user_id,
        data="nt:back_to_flags:",
    )
    await dispatcher_with_inject.feed_raw_update(bot, update)

    assert "EditMessageText" in mocked_session.method_names()
    key = StorageKey(bot_id=bot.id, chat_id=chat_id, user_id=user_id)
    assert await storage.get_state(key) == NewTriggerStates.configuring_flags.state


@pytest.mark.asyncio
async def test_dm_fallthrough_in_awaiting_key_shows_reminder(
    dispatcher_with_inject: Dispatcher,
    bot: Bot,
    mocked_session: MockedSession,
    storage: MemoryStorage,
) -> None:
    """В awaiting_key пришёл стикер (не текст) → handle_key_received не сматчился
    из-за F.text → fallthrough посылает reminder через SendMessage."""
    user_id, chat_id = 42, 42

    await _set_state_directly(
        storage,
        bot=bot,
        chat_id=chat_id,
        user_id=user_id,
        state=NewTriggerStates.awaiting_key.state,
        data={"chat_id": -1, "source": "lobby"},
    )

    update = build_update_message(
        update_id=50, message_id=200, chat_id=chat_id, user_id=user_id,
        sticker={
            "file_id": "stub", "file_unique_id": "u",
            "type": "regular", "width": 100, "height": 100, "is_animated": False, "is_video": False,
        },
    )
    await dispatcher_with_inject.feed_raw_update(bot, update)

    names = mocked_session.method_names()
    assert "SendMessage" in names, (
        f"Ожидался reminder про текст ключа. Calls: {names}"
    )
    # state не должен поменяться
    key = StorageKey(bot_id=bot.id, chat_id=chat_id, user_id=user_id)
    assert await storage.get_state(key) == NewTriggerStates.awaiting_key.state


@pytest.mark.asyncio
async def test_full_dm_lobby_to_awaiting_key_via_dispatcher(
    dispatcher_with_inject: Dispatcher,
    bot: Bot,
    mocked_session: MockedSession,
    storage: MemoryStorage,
    db_session,
) -> None:
    """End-to-end: /newtrigger в ЛС → выбор чата → отправка стикера → ввод ключа.
    Ключевая регрессия из прода (стикер контент → key "привет" → клава не появляется).
    """
    from tests.factories import create_chat, create_user, create_user_chat

    user = await create_user(db_session)
    chat = await create_chat(db_session, admins_only_add=False, title="Test Group")
    await create_user_chat(db_session, user_id=user.id, chat_id=chat.id, is_admin=False)

    user_id, chat_id = user.id, user.id

    # 1. /newtrigger в ЛС → должен показать lobby
    await dispatcher_with_inject.feed_raw_update(
        bot,
        build_update_message(
            update_id=1, message_id=1, chat_id=chat_id, user_id=user_id, text="/newtrigger"
        ),
    )
    assert "SendMessage" in mocked_session.method_names(), "lobby не отрисовался"

    key = StorageKey(bot_id=bot.id, chat_id=chat_id, user_id=user_id)
    assert await storage.get_state(key) == NewTriggerStates.choosing_chat.state

    mocked_session.reset()

    # 2. Выбор чата — потребует live get_chat_member. Замокаем.
    from aiogram.types import ChatMember, ChatMemberMember
    mocked_session.add_response(
        "GetChatMember",
        ChatMemberMember(user=__import__("aiogram").types.User(
            id=user_id, is_bot=False, first_name="Test"
        )),
    )

    await dispatcher_with_inject.feed_raw_update(
        bot,
        build_update_callback(
            update_id=2, cb_id="cb-chat", chat_id=chat_id, user_id=user_id,
            data=f"nt:chat:{chat.id}",
        ),
    )

    assert await storage.get_state(key) == NewTriggerStates.awaiting_content.state
    mocked_session.reset()

    # 3. Отправка стикера как контента
    await dispatcher_with_inject.feed_raw_update(
        bot,
        build_update_message(
            update_id=3, message_id=3, chat_id=chat_id, user_id=user_id,
            sticker={
                "file_id": "stub", "file_unique_id": "u",
                "type": "regular", "width": 100, "height": 100,
                "is_animated": False, "is_video": False,
            },
        ),
    )
    assert "SendMessage" in mocked_session.method_names(), "После стикера должен быть prompt про ключ"
    assert await storage.get_state(key) == NewTriggerStates.awaiting_key.state
    mocked_session.reset()

    # 4. Ввод ключа — здесь юзер сообщил что клава флагов не появилась
    await dispatcher_with_inject.feed_raw_update(
        bot,
        build_update_message(
            update_id=4, message_id=4, chat_id=chat_id, user_id=user_id, text="привет"
        ),
    )

    names = mocked_session.method_names()
    assert "SendMessage" in names, (
        f"После ввода ключа должна прийти клава флагов через sendMessage. Calls: {names}"
    )
    assert "EditMessageText" not in names, (
        "Бот НЕ должен пытаться editMessageText на сообщении юзера. "
        f"Calls: {names}"
    )

    # Проверим что в SendMessage есть клавиатура с radio-кнопками флагов
    send_msgs = mocked_session.payloads_for("SendMessage")
    found_flag_keyboard = False
    for m in send_msgs:
        rm = m.get("reply_markup", {})
        for row in rm.get("inline_keyboard", []):
            for btn in row:
                cd = btn.get("callback_data", "")
                if cd.startswith("nt:flag:") or cd == "nt:next:":
                    found_flag_keyboard = True
                    break
    assert found_flag_keyboard, (
        f"В SendMessage после ключа нет клавы флагов. Payloads: {send_msgs}"
    )

    assert await storage.get_state(key) == NewTriggerStates.configuring_flags.state
