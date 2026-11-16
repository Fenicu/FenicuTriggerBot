"""/add отказывается сохранять служебные сообщения: Telegram не умеет их копировать."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.trigger import Trigger
from tests.factories import create_chat, create_user

_USER = {"id": 1, "is_bot": False, "first_name": "U"}
_CHAT = {"id": -100, "type": "supergroup", "title": "T"}
_BASE = {"message_id": 5, "date": 1700000000, "chat": _CHAT, "from": _USER}

SERVICE_MESSAGES = {
    "new_chat_members": {"new_chat_members": [_USER]},
    "left_chat_member": {"left_chat_member": _USER},
    "new_chat_title": {"new_chat_title": "New title"},
    "new_chat_photo": {"new_chat_photo": [{"file_id": "f", "file_unique_id": "u", "width": 1, "height": 1}]},
    "delete_chat_photo": {"delete_chat_photo": True},
    "pinned_message": {"pinned_message": {**_BASE, "message_id": 4, "text": "pinned"}},
    "forum_topic_created": {"forum_topic_created": {"name": "Topic", "icon_color": 7322096}},
    "forum_topic_edited": {"forum_topic_edited": {"name": "Renamed"}},
    "forum_topic_closed": {"forum_topic_closed": {}},
    "forum_topic_reopened": {"forum_topic_reopened": {}},
    "video_chat_scheduled": {"video_chat_scheduled": {"start_date": 1700000100}},
    "video_chat_started": {"video_chat_started": {}},
    "video_chat_ended": {"video_chat_ended": {"duration": 60}},
    "video_chat_participants_invited": {"video_chat_participants_invited": {"users": [_USER]}},
    "message_auto_delete_timer_changed": {"message_auto_delete_timer_changed": {"message_auto_delete_time": 60}},
    "migrate_to_chat_id": {"migrate_to_chat_id": -100123},
}

COPYABLE_MESSAGES = {
    "text": {"text": "hello"},
    "photo": {"photo": [{"file_id": "f", "file_unique_id": "u", "width": 1, "height": 1}], "caption": "c"},
    "sticker": {
        "sticker": {
            "file_id": "f",
            "file_unique_id": "u",
            "type": "regular",
            "width": 1,
            "height": 1,
            "is_animated": False,
            "is_video": False,
        }
    },
    "dice": {"dice": {"emoji": "🎲", "value": 3}},
    "location": {"location": {"latitude": 1.0, "longitude": 2.0}},
}


def _make_i18n() -> MagicMock:
    i18n = MagicMock()
    i18n.trigger.add.unsupported.return_value = "Unsupported content"
    i18n.trigger.added.return_value = "Trigger added"
    return i18n


def _command_message(chat_id: int, user_id: int, reply: Message) -> MagicMock:
    message = MagicMock()
    message.chat = MagicMock(id=chat_id)
    message.sender_chat = None
    message.from_user = MagicMock(id=user_id)
    message.answer = AsyncMock()
    message.reply_to_message = reply
    return message


@pytest.fixture
async def chat(db_session: AsyncSession):
    return await create_chat(db_session, is_trusted=True)


@pytest.fixture
async def user(db_session: AsyncSession):
    return await create_user(db_session)


@pytest.mark.parametrize("kind", sorted(SERVICE_MESSAGES))
async def test_add_refuses_service_message(db_session: AsyncSession, chat, user, kind):
    from app.bot.handlers.creation import add_trigger

    reply = Message.model_validate({**_BASE, **SERVICE_MESSAGES[kind]})
    message = _command_message(chat.id, user.id, reply)

    await add_trigger(message, MagicMock(args="svc"), db_session, _make_i18n(), chat, user)

    message.answer.assert_awaited_once()
    assert message.answer.call_args.args[0] == "Unsupported content"
    assert (await db_session.execute(select(Trigger).where(Trigger.chat_id == chat.id))).scalars().first() is None


@pytest.mark.parametrize("kind", sorted(COPYABLE_MESSAGES))
async def test_add_still_accepts_copyable_message(db_session: AsyncSession, chat, user, kind):
    from app.bot.handlers.creation import add_trigger

    reply = Message.model_validate({**_BASE, **COPYABLE_MESSAGES[kind]})
    message = _command_message(chat.id, user.id, reply)

    await add_trigger(message, MagicMock(args=f"ok_{kind}"), db_session, _make_i18n(), chat, user)

    assert message.answer.call_args.args[0] == "Trigger added"
    assert (await db_session.execute(select(Trigger).where(Trigger.chat_id == chat.id))).scalars().first() is not None


def test_unsupported_key_exists_in_all_locales():
    for locale in ("ru", "en"):
        text = Path(f"locales/{locale}/messages.ftl").read_text(encoding="utf-8")
        assert "\ntrigger-add-unsupported = " in text, locale
