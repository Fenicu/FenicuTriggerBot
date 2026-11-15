from unittest.mock import AsyncMock

from sqlalchemy import select

from app.bot.handlers.chat_member import on_chat_member_update
from app.db.models.captcha_session import CaptchaSessionStatus
from app.db.models.user_chat import UserChat
from tests.factories import create_chat, create_user
from tests.handlers.test_captcha_ephemeral import (
    CHAT_ID,
    USER_ID,
    _make_i18n,
    _make_join_event,
    _make_mock_bot,
    _seed_session,
)
from app.worker.captcha import kick_unverified_user


async def test_manual_unmute_finalizes_pending_captcha_and_prevents_kick(db_session, monkeypatch):
    await create_chat(db_session, id=CHAT_ID, captcha_enabled=True)
    await create_user(db_session, id=USER_ID)
    captcha = await _seed_session(db_session, message_id=101, ephemeral_message_id=102)
    bot = _make_mock_bot()
    monkeypatch.setattr("app.bot.handlers.chat_member.bot", bot)
    monkeypatch.setattr("app.worker.captcha.bot", bot)
    event = _make_join_event(CHAT_ID, USER_ID)
    event.old_chat_member.status = "restricted"

    await on_chat_member_update(event, db_session, _make_i18n())

    await db_session.refresh(captcha)
    assert captcha.status == CaptchaSessionStatus.PASSED
    marker = await db_session.scalar(select(UserChat).where(UserChat.user_id == USER_ID, UserChat.chat_id == CHAT_ID))
    assert marker.captcha_passed_at is not None
    bot.delete_message.assert_awaited_once()
    bot.delete_ephemeral_message.assert_awaited_once()
    await kick_unverified_user(CHAT_ID, USER_ID, captcha.id)
    bot.ban_chat_member.assert_not_awaited()
