from unittest.mock import AsyncMock

import pytest
from app.db.models.captcha_session import CaptchaSessionKind
from app.db.models.user_chat import UserChat
from sqlalchemy import select

from tests.api.test_captcha_token import captcha_client  # noqa: F401
from tests.factories import create_captcha_session, create_chat, create_user


@pytest.mark.parametrize("kind", [CaptchaSessionKind.CHAT, CaptchaSessionKind.JOIN_REQUEST])
async def test_webapp_pass_creates_chat_marker(db_session, captcha_client, monkeypatch, kind):
    chat = await create_chat(db_session, captcha_enabled=True, captcha_type="webapp")
    user = await create_user(db_session)
    extra = {"join_request_query_id": "q-pass"} if kind == CaptchaSessionKind.JOIN_REQUEST else {}
    captcha = await create_captcha_session(db_session, chat.id, user.id, kind=kind, **extra)
    await db_session.commit()
    monkeypatch.setattr("app.api.v1.endpoints.captcha.bot.restrict_chat_member", AsyncMock())
    monkeypatch.setattr("app.api.v1.endpoints.captcha.bot.answer_chat_join_request_query", AsyncMock())

    async with captcha_client(user.id) as client:
        response = await client.post("/api/v1/captcha/solve", json={"token": captcha.token})

    assert response.status_code == 200
    marker = await db_session.scalar(select(UserChat).where(UserChat.user_id == user.id, UserChat.chat_id == chat.id))
    assert marker is not None
    assert marker.captcha_passed_at is not None


async def test_approve_server_error_compensates_with_timeout(db_session, captcha_client, monkeypatch):
    from aiogram.exceptions import TelegramServerError
    from unittest.mock import MagicMock
    from app.db.models.captcha_session import CaptchaSessionStatus

    chat = await create_chat(db_session)
    user = await create_user(db_session)
    captcha = await create_captcha_session(
        db_session, chat.id, user.id, kind=CaptchaSessionKind.JOIN_REQUEST, join_request_query_id="q-server"
    )
    await db_session.commit()
    monkeypatch.setattr(
        "app.api.v1.endpoints.captcha.bot.answer_chat_join_request_query",
        AsyncMock(side_effect=TelegramServerError(method=MagicMock(), message="Server unavailable")),
    )
    publish = AsyncMock()
    monkeypatch.setattr("app.api.v1.endpoints.captcha.broker.publish", publish)

    async with captcha_client(user.id) as client:
        response = await client.post("/api/v1/captcha/solve", json={"token": captcha.token})

    assert response.status_code == 503
    await db_session.refresh(captcha)
    assert captcha.status == CaptchaSessionStatus.PENDING
    assert publish.await_args.kwargs["routing_key"] == "q.captcha.joinreq_timeout"
