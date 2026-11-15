from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import Message, User

from app.bot.handlers import creation_private as wizard


class I18n:
    def __init__(self, path=""):
        self.path = path

    def __getattr__(self, name):
        return I18n(f"{self.path}.{name}".lstrip("."))

    def __call__(self, **kwargs):
        return f"{self.path}{kwargs}"


def bot():
    b = AsyncMock()
    b.get_chat_member.side_effect = TelegramRetryAfter(method=MagicMock(), message="Wait", retry_after=17)
    return b


def callback():
    cb = MagicMock()
    cb.from_user = User(id=42, is_bot=False, first_name="Alice")
    cb.answer = AsyncMock()
    cb.message.edit_text = AsyncMock()
    return cb


def session():
    s = AsyncMock()
    s.get.return_value = SimpleNamespace(id=-100, is_active=True, admins_only_add=False)
    return s


async def test_deep_link_rate_limit_shows_retry_feedback_without_state_change(monkeypatch):
    reply = AsyncMock()
    monkeypatch.setattr(Message, "answer", reply)
    msg = Message.model_validate(
        {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 42, "type": "private"},
            "from": {"id": 42, "is_bot": False, "first_name": "Alice"},
        }
    )
    state = AsyncMock()
    state.get_state.return_value = None
    await wizard.start_from_deep_link(msg, -100, state, session(), bot(), I18n())
    assert "retry.after" in reply.call_args.args[0]
    assert "17" in reply.call_args.args[0]
    state.set_state.assert_not_awaited()


async def test_chat_picker_rate_limit_preserves_selection_step():
    cb = callback()
    state = AsyncMock()
    await wizard.handle_chat_picked(
        cb,
        wizard.NewTriggerCB(action="chat", value="-100"),
        state,
        session(),
        bot(),
        I18n(),
    )
    assert "retry.after" in cb.answer.call_args.args[0]
    assert "17" in cb.answer.call_args.args[0]
    state.clear.assert_not_awaited()
    state.set_state.assert_not_awaited()


async def test_save_rate_limit_releases_lock_and_preserves_wizard(monkeypatch):
    cb = callback()
    state = AsyncMock()
    state.get_data.return_value = {
        "chat_id": -100,
        "content": {"text": "hi"},
        "key_phrase": "k",
        "match_type": "exact",
        "is_case_sensitive": False,
        "access_level": "all",
        "is_template": False,
    }
    vk = AsyncMock()
    vk.set.return_value = True
    monkeypatch.setattr(wizard, "valkey", vk)
    create = AsyncMock()
    monkeypatch.setattr(wizard.trigger_service, "create_trigger", create)
    await wizard.handle_save(cb, state, session(), bot(), I18n())
    assert "retry.after" in cb.answer.call_args.args[0]
    assert "17" in cb.answer.call_args.args[0]
    state.clear.assert_not_awaited()
    state.set_state.assert_not_awaited()
    vk.eval.assert_awaited_once()
    create.assert_not_awaited()
