from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, User

from app.bot.handlers import creation_private as wizard


class I18n:
    def __init__(self, path=""):
        self.path = path

    def __getattr__(self, name):
        return I18n(f"{self.path}.{name}".lstrip("."))

    def __call__(self, **kwargs):
        return self.path


def callback():
    cb = MagicMock()
    cb.from_user = User(id=42, is_bot=False, first_name="Alice")
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    return cb


def message():
    return Message.model_validate(
        {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 42, "type": "private"},
            "from": {"id": 42, "is_bot": False, "first_name": "Alice"},
        }
    )


@pytest.fixture
async def saved_state(monkeypatch):
    storage = MemoryStorage()
    state = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=42, user_id=42))
    await state.set_state(wizard.NewTriggerStates.confirming)
    await state.set_data(
        {
            "chat_id": -100,
            "content": {"text": "hi"},
            "key_phrase": "k",
            "match_type": "exact",
            "is_case_sensitive": False,
            "access_level": "all",
            "is_template": False,
        }
    )
    monkeypatch.setattr(wizard, "_save_via_wizard", AsyncMock(return_value=wizard.SaveResult(status="ok")))
    await wizard.handle_save(callback(), state, AsyncMock(), AsyncMock(), I18n())
    assert await state.get_state() == wizard.NewTriggerStates.saved.state
    yield state
    await storage.close()


async def test_deep_link_after_save_starts_without_conflict(saved_state, monkeypatch):
    reply = AsyncMock()
    monkeypatch.setattr(Message, "answer", reply)
    session = AsyncMock()
    session.get.return_value = SimpleNamespace(id=-200, title="New chat", is_active=True, admins_only_add=False)
    bot = AsyncMock()
    bot.get_chat_member.return_value = SimpleNamespace(status="member")
    await wizard.start_from_deep_link(message(), -200, saved_state, session, bot, I18n())
    assert await saved_state.get_state() == wizard.NewTriggerStates.awaiting_content.state
    assert (await saved_state.get_data())["chat_id"] == -200
    assert reply.call_args.args[0] == "new.trigger.content.prompt"


async def test_lobby_after_save_starts_without_conflict(saved_state, monkeypatch):
    reply = AsyncMock()
    monkeypatch.setattr(Message, "answer", reply)
    chat = SimpleNamespace(id=-200, title="New chat")
    monkeypatch.setattr(wizard, "_list_eligible_chats", AsyncMock(return_value=([chat], 1)))
    await wizard.newtrigger_dm_entry(message(), saved_state, AsyncMock(), I18n())
    assert await saved_state.get_state() == wizard.NewTriggerStates.choosing_chat.state
    assert reply.call_args.args[0] == "new.trigger.lobby.title"


async def test_cancel_after_save_behaves_like_no_active_wizard(saved_state, monkeypatch):
    reply = AsyncMock()
    monkeypatch.setattr(Message, "answer", reply)
    await wizard.handle_cancel_command(message(), saved_state, I18n())
    reply.assert_not_awaited()
    cb = callback()
    await wizard.handle_cancel_callback(cb, saved_state, I18n())
    cb.answer.assert_awaited_once_with()
    cb.message.edit_text.assert_not_awaited()
