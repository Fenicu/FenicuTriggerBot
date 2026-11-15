from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.bot.handlers.captcha import _handle_success
from app.bot.handlers.chat_member import on_chat_member_update
from app.bot.handlers.join_request import on_chat_join_request
from app.db.models.user_chat import UserChat
from sqlalchemy import select

from tests.factories import create_chat, create_user
from tests.handlers.test_captcha_ephemeral import (
    CHAT_ID,
    USER_ID,
    _make_callback,
    _make_i18n,
    _make_join_event,
    _make_mock_bot,
    _seed_session,
)
from tests.handlers.test_join_request import _make_event


@pytest.mark.parametrize("entry", ["member", "request"])
async def test_global_pass_does_not_bypass_another_chat(db_session, monkeypatch, entry):
    chat = await create_chat(db_session, id=CHAT_ID, captcha_enabled=True, captcha_type="emoji")
    user = await create_user(db_session, id=USER_ID, has_passed_captcha=True)
    await db_session.commit()
    bot = _make_mock_bot()
    bot.send_chat_join_request_web_app = AsyncMock()
    bot.answer_chat_join_request_query = AsyncMock()
    module = "chat_member" if entry == "member" else "join_request"
    monkeypatch.setattr(f"app.bot.handlers.{module}.bot", bot)
    monkeypatch.setattr(f"app.bot.handlers.{module}.broker", MagicMock(publish=AsyncMock()))

    if entry == "member":
        await on_chat_member_update(_make_join_event(CHAT_ID, USER_ID), db_session, _make_i18n())
        bot.restrict_chat_member.assert_awaited()
    else:
        await on_chat_join_request(_make_event(CHAT_ID, USER_ID), db_session, chat, user)
        bot.send_chat_join_request_web_app.assert_awaited_once()
        bot.answer_chat_join_request_query.assert_not_awaited()


@pytest.mark.parametrize("entry", ["member", "request"])
async def test_chat_pass_bypasses_only_that_chat(db_session, monkeypatch, entry):
    chat = await create_chat(db_session, id=CHAT_ID, captcha_enabled=True, captcha_type="emoji")
    user = await create_user(db_session, id=USER_ID)
    db_session.add(UserChat(user_id=USER_ID, chat_id=CHAT_ID, captcha_passed_at=datetime.now(UTC)))
    await db_session.commit()
    bot = _make_mock_bot()
    bot.answer_chat_join_request_query = AsyncMock()
    bot.send_chat_join_request_web_app = AsyncMock()
    module = "chat_member" if entry == "member" else "join_request"
    monkeypatch.setattr(f"app.bot.handlers.{module}.bot", bot)

    if entry == "member":
        await on_chat_member_update(_make_join_event(CHAT_ID, USER_ID), db_session, _make_i18n())
        bot.restrict_chat_member.assert_not_awaited()
    else:
        await on_chat_join_request(_make_event(CHAT_ID, USER_ID), db_session, chat, user)
        bot.answer_chat_join_request_query.assert_awaited_once_with(
            chat_join_request_query_id="query-1", result="approve"
        )


async def test_emoji_pass_creates_chat_marker(db_session, monkeypatch):
    await create_chat(db_session, id=CHAT_ID, captcha_enabled=True)
    await create_user(db_session, id=USER_ID)
    await _seed_session(db_session)
    monkeypatch.setattr("app.bot.handlers.captcha.bot", _make_mock_bot())
    monkeypatch.setattr("app.bot.handlers.captcha.schedule_autodelete", AsyncMock())

    await _handle_success(_make_callback(), db_session, _make_i18n())

    marker = await db_session.scalar(select(UserChat).where(UserChat.user_id == USER_ID, UserChat.chat_id == CHAT_ID))
    assert marker is not None
    assert marker.captcha_passed_at is not None
