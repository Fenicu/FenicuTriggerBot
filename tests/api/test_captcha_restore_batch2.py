from unittest.mock import AsyncMock

from tests.api.test_captcha_token import captcha_client  # noqa: F401
from tests.factories import create_captcha_session, create_chat, create_user


async def test_webapp_restore_failure_queues_retry_and_continues_cleanup(db_session, captcha_client, monkeypatch):
    from aiogram.exceptions import TelegramNetworkError
    from unittest.mock import MagicMock

    chat = await create_chat(db_session)
    user = await create_user(db_session)
    captcha = await create_captcha_session(db_session, chat.id, user.id, message_id=101)
    await db_session.commit()
    monkeypatch.setattr(
        "app.api.v1.endpoints.captcha.bot.restrict_chat_member",
        AsyncMock(side_effect=TelegramNetworkError(method=MagicMock(), message="Offline")),
    )
    cleanup = AsyncMock()
    monkeypatch.setattr("app.api.v1.endpoints.captcha.bot.edit_message_text", cleanup)
    publish = AsyncMock()
    monkeypatch.setattr("app.core.safe_telegram.broker.publish", publish)

    async with captcha_client(user.id) as client:
        response = await client.post("/api/v1/captcha/solve", json={"token": captcha.token})

    assert response.status_code == 200
    assert publish.await_args.kwargs["routing_key"] == "q.captcha.restore"
    cleanup.assert_awaited_once()
