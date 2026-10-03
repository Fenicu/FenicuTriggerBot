"""Контент триггера/приветствия должен валидироваться обратно в Message.

Регресс: сериализация с exclude_defaults выкидывала дискриминатор `type` у
forward_origin / external_reply.origin, и Message.model_validate падал с
union_tag_not_found -- триггер молча не срабатывал.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message

from tests.handlers.test_creation_private import _i18n_runner

_DATE = 1_700_000_000

ORIGINS = {
    "user": {
        "type": "user",
        "date": _DATE,
        "sender_user": {"id": 111, "is_bot": False, "first_name": "Alice"},
    },
    "hidden_user": {
        "type": "hidden_user",
        "date": _DATE,
        "sender_user_name": "Hidden Bob",
    },
    "chat": {
        "type": "chat",
        "date": _DATE,
        "sender_chat": {"id": -100222, "type": "supergroup", "title": "Group"},
    },
    "channel": {
        "type": "channel",
        "date": _DATE,
        "chat": {"id": -100333, "type": "channel", "title": "Channel"},
        "message_id": 7,
    },
}


def _tg_message(text: str = "hello", **extra) -> Message:
    """Message в том виде, в каком его парсит aiogram из апдейта Telegram."""
    data = {
        "message_id": 10,
        "date": _DATE,
        "chat": {"id": 42, "type": "private", "first_name": "Alice"},
        "from": {"id": 42, "is_bot": False, "first_name": "Alice"},
        "text": text,
        **extra,
    }
    return Message.model_validate(data)


def _cases():
    for origin_type, origin in ORIGINS.items():
        yield pytest.param({"forward_origin": origin}, "forward_origin", origin_type, id=f"forward-{origin_type}")
        yield pytest.param(
            {"external_reply": {"origin": origin}}, "external_reply", origin_type, id=f"ext-{origin_type}"
        )


def _origin_type(msg: Message, field: str) -> str:
    origin = msg.forward_origin if field == "forward_origin" else msg.external_reply.origin
    return origin.type


@pytest.mark.parametrize(("extra", "field", "origin_type"), list(_cases()))
async def test_add_trigger_content_roundtrips(extra, field, origin_type):
    from app.bot.handlers.creation import add_trigger

    message = MagicMock()
    message.chat = MagicMock(id=-100123)
    message.chat.get_member = AsyncMock(return_value=MagicMock(status="administrator"))
    message.from_user = MagicMock(id=42)
    message.answer = AsyncMock()
    message.reply_to_message = _tg_message(**extra)
    command = MagicMock(args="hello")
    db_chat = MagicMock(is_trusted=True)

    with patch("app.bot.handlers.creation.create_trigger", new_callable=AsyncMock) as mock_create:
        await add_trigger(message, command, MagicMock(), MagicMock(), db_chat, MagicMock())

    content = mock_create.await_args.kwargs["content"]
    assert _origin_type(Message.model_validate(content), field) == origin_type


def _dm_message(real: Message) -> MagicMock:
    msg = MagicMock()
    msg.chat = MagicMock(id=42, type="private")
    msg.from_user = MagicMock(id=42)
    msg.text = real.text
    msg.caption = None
    msg.game = None
    msg.paid_media = None
    msg.rich_message = None
    msg.answer = AsyncMock()
    msg.model_dump_json = MagicMock(side_effect=real.model_dump_json)
    return msg


@pytest.mark.parametrize("text", ["hello", "/cmd"], ids=["content", "command-like"])
@pytest.mark.parametrize(("extra", "field", "origin_type"), list(_cases()))
async def test_wizard_content_roundtrips(extra, field, origin_type, text):
    from app.bot.handlers.creation_private import handle_content_received

    msg = _dm_message(_tg_message(text=text, **extra))
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"chat_id": -100, "source": "lobby"})

    await handle_content_received(msg, state=state, i18n=_i18n_runner())

    kwargs = state.update_data.await_args.kwargs
    content = kwargs.get("content") or kwargs["pending_content"]
    assert _origin_type(Message.model_validate(content), field) == origin_type


@pytest.mark.parametrize(("extra", "field", "origin_type"), list(_cases()))
async def test_welcome_content_roundtrips(extra, field, origin_type):
    from app.bot.handlers.welcome import welcome_command

    msg = MagicMock()
    msg.chat = MagicMock(id=-100123, type="supergroup")
    msg.from_user = MagicMock(id=42)
    msg.answer = AsyncMock()
    msg.chat.get_member = AsyncMock(return_value=MagicMock(status="administrator"))
    msg.reply_to_message = _tg_message(**extra)
    db_chat = MagicMock(id=-100123, autodelete_settings={})

    with patch("app.bot.handlers.welcome.update_chat_settings", new_callable=AsyncMock) as mock_update:
        await welcome_command(msg, MagicMock(args="set"), MagicMock(), MagicMock(), db_chat)

    content = mock_update.await_args.kwargs["welcome_message"]
    assert _origin_type(Message.model_validate(content), field) == origin_type
