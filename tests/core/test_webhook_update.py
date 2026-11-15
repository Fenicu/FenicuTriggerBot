"""Вебхук: Update парсится с bot-контекстом и переживает link_preview_options."""

from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.dispatcher.event.bases import UNHANDLED
from aiogram.types import Update
from app.main import dp

BOT_TOKEN = "0000000000:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"  # noqa: S105


def _link_preview_update() -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "date": 1700000000,
            "chat": {"id": 123, "type": "private"},
            "from": {"id": 123, "is_bot": False, "first_name": "A"},
            "text": "https://example.com",
            "link_preview_options": {"url": "https://example.com"},
        },
    }


async def test_webhook_update_with_link_preview_keeps_bot_context(monkeypatch: pytest.MonkeyPatch) -> None:
    bot = Bot(token=BOT_TOKEN)
    wrap_outer = AsyncMock(return_value=UNHANDLED)
    monkeypatch.setattr(dp.update, "wrap_outer_middleware", wrap_outer)

    update = Update.model_validate(_link_preview_update(), context={"bot": bot})
    assert update.bot is bot

    await dp.feed_webhook_update(bot, update)

    wrap_outer.assert_awaited_once()
    fed_update = wrap_outer.await_args.args[1]
    assert fed_update.bot is bot
    assert fed_update.message.link_preview_options.url == "https://example.com"
    await bot.session.close()
