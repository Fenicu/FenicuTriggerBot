from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from app.db.models.captcha_session import CaptchaSessionKind, CaptchaSessionStatus
from app.worker.captcha import expire_join_request
from tests.factories import create_captcha_session, create_chat, create_user


async def test_early_join_request_timeout_republishes_until_deadline(db_session, monkeypatch):
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    captcha = await create_captcha_session(
        db_session,
        chat.id,
        user.id,
        kind=CaptchaSessionKind.JOIN_REQUEST,
        join_request_query_id="q-early",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    await db_session.commit()
    bot = MagicMock(answer_chat_join_request_query=AsyncMock(), ban_chat_member=AsyncMock())
    broker = MagicMock(publish=AsyncMock())
    monkeypatch.setattr("app.worker.captcha.bot", bot)
    monkeypatch.setattr("app.worker.captcha.broker", broker)

    await expire_join_request(chat.id, user.id, captcha.id)

    await db_session.refresh(captcha)
    assert captcha.status == CaptchaSessionStatus.PENDING
    bot.answer_chat_join_request_query.assert_not_awaited()
    bot.ban_chat_member.assert_not_awaited()
    assert 290_000 <= broker.publish.await_args.kwargs["headers"]["x-delay"] <= 300_000
    assert broker.publish.await_args.kwargs["routing_key"] == "q.captcha.joinreq_timeout"


async def test_never_delivered_captcha_expires_without_punishing_user(db_session, monkeypatch, caplog):
    from app.worker.captcha import kick_unverified_user
    from tests.handlers.test_captcha_ephemeral import _make_mock_bot

    chat = await create_chat(db_session)
    user = await create_user(db_session)
    captcha = await create_captcha_session(
        db_session,
        chat.id,
        user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        message_id=None,
        ephemeral_message_id=None,
    )
    await db_session.commit()
    bot = _make_mock_bot()
    monkeypatch.setattr("app.worker.captcha.bot", bot)

    await kick_unverified_user(chat.id, user.id, captcha.id)

    await db_session.refresh(captcha)
    assert captcha.status == CaptchaSessionStatus.EXPIRED
    bot.ban_chat_member.assert_not_awaited()
    bot.unban_chat_member.assert_not_awaited()
    bot.restrict_chat_member.assert_awaited_once()
    assert bot.restrict_chat_member.await_args.kwargs["permissions"].can_send_messages is True
    assert "never delivered" in caplog.text
