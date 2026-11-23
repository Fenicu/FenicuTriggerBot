"""Вебхук не должен отвечать 500 на апдейт, который не проходит валидацию.

Telegram на 500 повторяет тот же апдейт, поэтому невалидный payload надо
подтверждать 200 и логировать один раз, как это делает сам aiogram с 3.33.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Update
from httpx import ASGITransport, AsyncClient

import app.main as main_module

VALID_UPDATE = {
    "update_id": 100,
    "message": {
        "message_id": 1,
        "date": 1700000000,
        "chat": {"id": 42, "type": "private"},
        "from": {"id": 42, "is_bot": False, "first_name": "Test"},
        "text": "hi",
    },
}


def _client(*, raise_app_exceptions: bool = True) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=main_module.app, raise_app_exceptions=raise_app_exceptions),
        base_url="http://test",
    )


@pytest.fixture
def webhook_env():
    """Подменить глобальные bot/dispatcher из app.main (они импортированы по значению)."""
    bot = MagicMock()
    dp = MagicMock()
    dp.feed_webhook_update = AsyncMock()
    with (
        patch.object(main_module, "bot", bot),
        patch.object(main_module, "dp", dp),
    ):
        yield bot, dp


async def test_invalid_payload_returns_ok_and_is_not_fed(webhook_env, caplog):
    _, dp = webhook_env
    payload = {"update_id": 4242, "message": {"text": "payload-marker"}}

    with caplog.at_level(logging.WARNING):
        async with _client() as client:
            response = await client.post(
                main_module.settings.WEBHOOK_PATH,
                json=payload,
                headers={"X-Telegram-Bot-Api-Secret-Token": main_module.settings.SECRET_TOKEN},
            )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    dp.feed_webhook_update.assert_not_awaited()
    assert "4242" in caplog.text
    assert "payload-marker" not in caplog.text


async def test_invalid_payload_logs_single_warning_with_first_error_location(webhook_env, caplog):
    payload = {"update_id": 7, "message": {"text": "x"}}

    with caplog.at_level(logging.WARNING):
        async with _client() as client:
            await client.post(
                main_module.settings.WEBHOOK_PATH,
                json=payload,
                headers={"X-Telegram-Bot-Api-Secret-Token": main_module.settings.SECRET_TOKEN},
            )

    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "message" in warnings[0].getMessage()


async def test_valid_payload_is_fed_to_dispatcher(webhook_env):
    _, dp = webhook_env

    async with _client() as client:
        response = await client.post(
            main_module.settings.WEBHOOK_PATH,
            json=VALID_UPDATE,
            headers={"X-Telegram-Bot-Api-Secret-Token": main_module.settings.SECRET_TOKEN},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    dp.feed_webhook_update.assert_awaited_once()
    fed_update = dp.feed_webhook_update.await_args.args[1]
    assert isinstance(fed_update, Update)
    assert fed_update.update_id == 100


async def test_wrong_secret_is_rejected_before_parsing(webhook_env):
    _, dp = webhook_env

    async with _client() as client:
        response = await client.post(
            main_module.settings.WEBHOOK_PATH,
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "unauthorized"}
    dp.feed_webhook_update.assert_not_awaited()


async def test_handler_error_on_valid_update_still_surfaces(webhook_env):
    _, dp = webhook_env
    dp.feed_webhook_update.side_effect = RuntimeError("boom")

    async with _client(raise_app_exceptions=False) as client:
        response = await client.post(
            main_module.settings.WEBHOOK_PATH,
            json=VALID_UPDATE,
            headers={"X-Telegram-Bot-Api-Secret-Token": main_module.settings.SECRET_TOKEN},
        )

    assert response.status_code == 500
