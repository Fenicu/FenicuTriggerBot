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
