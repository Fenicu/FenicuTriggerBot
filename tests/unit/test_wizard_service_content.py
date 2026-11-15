from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message

from app.bot.handlers.creation_private import NewTriggerStates, handle_content_received


class I18n:
    def __getattr__(self, name):
        return self

    def __call__(self, **kwargs):
        return "Expected a content message. Send text, photo, video, GIF, sticker, document or voice."


USER = {"id": 42, "is_bot": False, "first_name": "Alice"}
BASE = {"message_id": 1, "date": 0, "chat": {"id": 42, "type": "private"}, "from": USER}


@pytest.mark.parametrize(
    "content",
    [
        {"new_chat_members": [USER]},
        {"left_chat_member": USER},
        {"new_chat_title": "New title"},
        {"delete_chat_photo": True},
        {"group_chat_created": True},
        {"supergroup_chat_created": True},
        {"channel_chat_created": True},
        {"migrate_to_chat_id": -100},
        {"pinned_message": {**BASE, "text": "Pinned text"}},
        {"forum_topic_created": {"name": "Topic", "icon_color": 123}},
        {"forum_topic_edited": {"name": "Topic"}},
        {"forum_topic_closed": {}},
        {"forum_topic_reopened": {}},
        {"general_forum_topic_hidden": {}},
        {"general_forum_topic_unhidden": {}},
        {"video_chat_started": {}},
        {"video_chat_ended": {"duration": 1}},
        {"video_chat_scheduled": {"start_date": 0}},
        {"video_chat_participants_invited": {"users": [USER]}},
        {"message_auto_delete_timer_changed": {"message_auto_delete_time": 30}},
        {"write_access_allowed": {}},
        {"web_app_data": {"data": "x", "button_text": "x"}},
        {},
    ],
)
async def test_uncopyable_message_is_refused_without_changing_state(content, monkeypatch):
    reply = AsyncMock()
    monkeypatch.setattr(Message, "answer", reply)
    state = AsyncMock()
    await handle_content_received(Message.model_validate({**BASE, **content}), state, I18n())
    state.set_state.assert_not_awaited()
    state.update_data.assert_not_awaited()
    assert "Expected a content message" in reply.call_args.args[0]


@pytest.mark.parametrize(
    "content",
    [
        {"text": "hello"},
        {"text": "/foo"},
        {"photo": [{"file_id": "photo", "file_unique_id": "unique", "width": 10, "height": 10}]},
        {
            "sticker": {
                "file_id": "s",
                "file_unique_id": "u",
                "type": "regular",
                "width": 10,
                "height": 10,
                "is_animated": False,
                "is_video": False,
            }
        },
        {"voice": {"file_id": "v", "file_unique_id": "u", "duration": 1}},
        {"contact": {"phone_number": "+100", "first_name": "A"}},
    ],
)
async def test_copyable_content_is_accepted_without_sending_a_copy(content, monkeypatch):
    monkeypatch.setattr(Message, "answer", AsyncMock())
    bot = MagicMock()
    msg = Message.model_validate({**BASE, **content}).as_(bot)
    state = AsyncMock()
    await handle_content_received(msg, state, I18n())
    state.update_data.assert_awaited_once()
    if content.get("text") != "/foo":
        state.set_state.assert_awaited_once_with(NewTriggerStates.awaiting_key)
    bot.assert_not_called()
