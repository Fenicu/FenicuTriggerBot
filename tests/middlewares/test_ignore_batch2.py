from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, ChatMemberLeft, ChatMemberMember, ChatMemberUpdated, Update, User

from app.bot.middlewares.ignore import IgnoreMiddleware


@pytest.mark.parametrize("actor_bot,member_bot,expected", [(True, False, True), (False, True, False)])
async def test_chat_member_filters_subject_instead_of_actor(actor_bot, member_bot, expected):
    member = User(id=10, is_bot=member_bot, first_name="Member")
    actor = User(id=20, is_bot=actor_bot, first_name="Approver")
    change = ChatMemberUpdated(
        chat=Chat(id=-10010, type="supergroup"),
        from_user=actor,
        date=datetime.now(timezone.utc),
        old_chat_member=ChatMemberLeft(user=member),
        new_chat_member=ChatMemberMember(user=member),
    )
    event = Update(update_id=1, chat_member=change)
    handler = AsyncMock()

    await IgnoreMiddleware()(handler, event, {"event_from_user": actor})

    assert handler.await_count == int(expected)
