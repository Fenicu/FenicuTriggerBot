from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message, RichMessage, User

from app.bot.handlers import creation_private as wizard


class I18n:
    def __init__(self, path=""):
        self.path = path

    def __getattr__(self, name):
        return I18n(f"{self.path}.{name}".lstrip("."))

    def __call__(self, **kwargs):
        return f"{self.path}{kwargs}"


def message(**content):
    return Message.model_validate(
        {
            "message_id": 1,
            "date": 0,
            "chat": {"id": 42, "type": "private"},
            "from": {"id": 42, "is_bot": False, "first_name": "Alice"},
            **content,
        }
    )


def callback():
    cb = MagicMock()
    cb.from_user = User(id=42, is_bot=False, first_name="Alice")
    cb.message.chat.id = 42
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


@pytest.mark.parametrize("text", ["{{ 2 ** 100 }}", "{% for x in xs %}x{% endfor %}", "{{ broken"])
async def test_rich_content_rejects_invalid_templates_before_storage(text, monkeypatch):
    rm = RichMessage.model_validate({"blocks": [{"type": "paragraph", "text": text}]})
    reply = AsyncMock()
    monkeypatch.setattr(Message, "answer", reply)
    state = AsyncMock()
    await wizard.handle_content_received(message(rich_message=rm), state, I18n())
    state.update_data.assert_not_awaited()
    state.set_state.assert_not_awaited()
    assert "content.wrong.type" in reply.call_args.args[0]


async def test_rich_preview_renders_even_without_template_flag():
    cb = callback()
    state = AsyncMock()
    state.get_data.return_value = {
        "chat_id": -100,
        "rich": True,
        "is_template": False,
        "content": {"text": "<p>{{ user.full_name }}: {{ chat.title }} / {{ vars.greeting }}</p>"},
    }
    session = AsyncMock()
    session.get.return_value = SimpleNamespace(title="Target chat", timezone="UTC")
    result = MagicMock()
    result.scalars.return_value = [SimpleNamespace(key="greeting", value="hello")]
    session.execute.return_value = result
    bot = AsyncMock()
    await wizard._render_preview(cb, state, session, bot, I18n())
    assert bot.send_rich_message.call_args.kwargs["rich_message"].html == "<p>Alice: Target chat / hello</p>"
    assert state.update_data.call_args is None
