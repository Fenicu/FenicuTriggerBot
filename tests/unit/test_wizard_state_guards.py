from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import User

from app.bot.handlers import creation_private as wizard


class I18n:
    def __init__(self, path=""):
        self.path = path

    def __getattr__(self, name):
        return I18n(f"{self.path}.{name}".lstrip("."))

    def __call__(self, **kwargs):
        return f"{self.path}{kwargs}"


def callback():
    cb = MagicMock()
    cb.from_user = User(id=42, is_bot=False, first_name="Alice")
    cb.message.chat.id = 42
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


@pytest.mark.parametrize("handler", [wizard.handle_again, wizard.handle_finish])
@pytest.mark.parametrize("current", [None, "OtherWizard:awaiting_content", "NewTriggerStates:nonexistent"])
async def test_old_completion_buttons_do_not_change_foreign_or_absent_state(handler, current):
    cb = callback()
    state = AsyncMock()
    state.get_state.return_value = current
    state.get_data.return_value = {"chat_id": -100}
    await handler(cb, state, I18n())
    state.clear.assert_not_awaited()
    state.set_state.assert_not_awaited()
    state.update_data.assert_not_awaited()
    cb.message.edit_text.assert_not_awaited()
    cb.answer.assert_awaited_once()


async def test_saved_wizard_keeps_state_for_completion_buttons(monkeypatch):
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
    monkeypatch.setattr(wizard, "_save_via_wizard", AsyncMock(return_value=wizard.SaveResult(status="ok")))
    await wizard.handle_save(cb, state, AsyncMock(), AsyncMock(), I18n())
    assert state.set_state.await_args.args[0].state in wizard.NewTriggerStates.__all_states__


@pytest.mark.parametrize("handler", [wizard.handle_again, wizard.handle_finish])
async def test_completion_buttons_work_for_own_state(handler):
    cb = callback()
    state = AsyncMock()
    state.get_state.return_value = wizard.NewTriggerStates.confirming.state
    state.get_data.return_value = {"chat_id": -100}
    await handler(cb, state, I18n())
    if handler is wizard.handle_again:
        state.set_state.assert_awaited_once_with(wizard.NewTriggerStates.awaiting_content)
    else:
        state.clear.assert_awaited_once()
