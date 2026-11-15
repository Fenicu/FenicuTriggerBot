from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.welcome_service import send_welcome_message
from tests.factories import create_chat


@pytest.mark.parametrize("field", ["text", "caption"])
async def test_literal_entities_reach_renderer_unchanged(db_session, monkeypatch, field):
    literal = "Use &lt;b&gt; literally &amp; safely"
    payload = {field: literal}
    if field == "caption":
        payload["photo"] = [{"file_id": "photo", "width": 1, "height": 1}]
    chat = await create_chat(db_session, welcome_enabled=True, welcome_message=payload)
    renderer = AsyncMock(return_value=literal)
    monkeypatch.setattr("app.services.welcome_service.render_template", renderer)
    monkeypatch.setattr("app.services.welcome_service.schedule_autodelete", AsyncMock())
    bot = MagicMock(send_message=AsyncMock(), send_photo=AsyncMock())

    await send_welcome_message(bot, db_session, MagicMock(id=chat.id), MagicMock(), chat)

    assert renderer.await_args.args[0] == literal
