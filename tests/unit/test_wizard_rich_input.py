# ruff: noqa: SLF001
import pytest
from aiogram.types import RichMessage
from unittest.mock import AsyncMock, MagicMock

from app.bot.handlers.creation_private import (
    NewTriggerStates,
    _render_preview,
    handle_content_received,
)


class _FakeI18n:
    def __getattr__(self, _):
        return _FakeI18n()

    def __call__(self, *a, **k):
        return "msg"


def _make_message(rich=None, game=None, paid=None, text=None):
    m = MagicMock()
    m.from_user.id = 1
    m.text = text
    m.caption = None
    m.sticker = None
    m.photo = None
    m.rich_message = rich
    m.game = game
    m.paid_media = paid
    m.answer = AsyncMock()
    m.model_dump_json = MagicMock(return_value="{}")
    return m


@pytest.mark.asyncio
async def test_rich_forward_stored_as_rich_content():
    rm = RichMessage.model_validate({"blocks": [{"type": "paragraph", "text": "hi"}]})
    msg = _make_message(rich=rm)
    state = AsyncMock()
    await handle_content_received(msg, state, _FakeI18n())
    # content сохранён как rich-html, флаг rich=True, переход к awaiting_key
    update_kwargs = state.update_data.call_args.kwargs
    assert update_kwargs["rich"] is True
    assert update_kwargs["content"] == {"text": "<p>hi</p>"}
    state.set_state.assert_awaited_with(NewTriggerStates.awaiting_key)


@pytest.mark.asyncio
async def test_game_rejected_without_state_change():
    msg = _make_message(game=MagicMock())
    state = AsyncMock()
    await handle_content_received(msg, state, _FakeI18n())
    state.set_state.assert_not_called()
    msg.answer.assert_awaited()  # показано content-wrong-type


@pytest.mark.asyncio
async def test_preview_uses_send_rich_for_rich_content():
    callback = MagicMock()
    callback.from_user = MagicMock(id=1)
    callback.message.chat.id = 100
    callback.answer = AsyncMock()
    callback.message.edit_text = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "content": {"text": "<p>hi</p>"}, "chat_id": 100, "rich": True, "is_template": False,
    })
    session = AsyncMock()
    session.get = AsyncMock(return_value=MagicMock(title="T"))
    bot = MagicMock()
    bot.send_rich_message = AsyncMock()
    bot.send_message = AsyncMock()
    await _render_preview(callback, state, session, bot, _FakeI18n())
    bot.send_rich_message.assert_awaited_once()
