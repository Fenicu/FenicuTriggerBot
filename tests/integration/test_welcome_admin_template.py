from unittest.mock import AsyncMock, MagicMock

import pytest
from app.services.welcome_service import send_welcome_message
from markupsafe import escape

from tests.factories import create_chat


@pytest.mark.parametrize("field", ["text", "caption"])
async def test_stored_admin_markup_renders_around_escaped_chat_title(db_session, monkeypatch, field):
    source = "Добро пожаловать в &lt;b&gt;{{ chat.title }}&lt;/b&gt;!"
    title = "Новости <&>"
    payload = {field: source}
    if field == "caption":
        payload["photo"] = [{"file_id": "photo", "width": 1, "height": 1}]
    chat = await create_chat(db_session, title=title, welcome_enabled=True, welcome_message=payload)
    # Экранирование значений — контракт сервиса шаблонов, проверяем сохранность контекста.
    monkeypatch.setattr(
        "app.services.welcome_service.get_render_context",
        lambda *args: {"chat": {"title": escape(title)}},
    )
    monkeypatch.setattr("app.services.welcome_service.schedule_autodelete", AsyncMock())
    bot = MagicMock(
        send_message=AsyncMock(return_value=MagicMock(message_id=42)),
        send_photo=AsyncMock(return_value=MagicMock(message_id=43)),
    )

    await send_welcome_message(bot, db_session, MagicMock(id=chat.id), MagicMock(), chat)

    sent = bot.send_message if field == "text" else bot.send_photo
    assert sent.await_args.kwargs[field] == "Добро пожаловать в <b>Новости &lt;&amp;&gt;</b>!"
