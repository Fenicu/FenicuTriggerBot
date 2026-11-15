from unittest.mock import AsyncMock

from tests.api.test_captcha_token import captcha_client  # noqa: F401
from tests.factories import create_captcha_session, create_chat, create_user


async def test_webapp_pass_deletes_both_captchas_and_sends_welcome(db_session, captcha_client, monkeypatch):
    chat = await create_chat(db_session, welcome_enabled=True, welcome_message={"text": "Welcome"})
    user = await create_user(db_session)
    captcha = await create_captcha_session(db_session, chat.id, user.id, message_id=101, ephemeral_message_id=102)
    await db_session.commit()
    monkeypatch.setattr("app.api.v1.endpoints.captcha.bot.restrict_chat_member", AsyncMock())
    public_delete = AsyncMock()
    ephemeral_delete = AsyncMock()
    monkeypatch.setattr("app.api.v1.endpoints.captcha.bot.delete_message", public_delete)
    monkeypatch.setattr("app.api.v1.endpoints.captcha.bot.delete_ephemeral_message", ephemeral_delete)
    welcome = AsyncMock()
    monkeypatch.setattr("app.services.welcome_service.send_welcome_message", welcome)

    async with captcha_client(user.id) as client:
        response = await client.post("/api/v1/captcha/solve", json={"token": captcha.token})

    assert response.status_code == 200
    public_delete.assert_awaited_once_with(chat.id, 101)
    ephemeral_delete.assert_awaited_once_with(chat_id=chat.id, receiver_user_id=user.id, ephemeral_message_id=102)
    welcome.assert_awaited_once()
    assert welcome.await_args.args[2].id == chat.id
    assert welcome.await_args.args[3].id == user.id
