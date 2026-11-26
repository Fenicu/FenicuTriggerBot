"""Регрессия gban: транзиентные сбои скачивания списка повторяются с backoff."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from app.services.gban_service import GbanService
from tests.integration.gban_fakes import FakePipeline, FakeResponse, FakeSession, session_factory

URL = "https://example.com/gban.json"


@pytest.fixture
def mock_valkey():
    with patch("app.services.gban_service.valkey") as m:
        m.hgetall = AsyncMock(return_value={})
        m.hset = AsyncMock()
        m.hdel = AsyncMock()
        m.delete = AsyncMock()
        m.unlink = AsyncMock()
        m.sadd = AsyncMock()
        m.rename = AsyncMock()
        m.exists = AsyncMock(return_value=0)
        m.pipeline = lambda **_kwargs: FakePipeline(m)
        yield m


async def test_retries_transient_error_then_succeeds(mock_valkey):
    failing = aiohttp.ClientConnectionError("Connection reset by peer")
    recovering = FakeResponse(body="[111, 222]")

    with (
        patch("app.services.gban_service.settings") as mock_settings,
        patch(
            "app.services.gban_service.aiohttp.ClientSession",
            side_effect=[failing, FakeSession([recovering])],
        ),
        patch("app.services.gban_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_settings.GBAN_LIST_URL = URL

        await GbanService.update_banlist()

    mock_sleep.assert_awaited_once()
    assert mock_valkey.hset.await_args.kwargs["mapping"]["count"] == 2


async def test_gives_up_after_three_attempts(mock_valkey):
    error = aiohttp.ClientConnectionError("Connection reset by peer")

    with (
        patch("app.services.gban_service.settings") as mock_settings,
        patch("app.services.gban_service.aiohttp.ClientSession", side_effect=error) as mock_session,
        patch("app.services.gban_service.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_settings.GBAN_LIST_URL = URL

        await GbanService.update_banlist()

    assert mock_session.call_count == 3
    mock_valkey.rename.assert_not_awaited()


async def test_transient_failure_logged_without_traceback(mock_valkey, caplog):
    error = aiohttp.ClientConnectionError("Connection reset by peer")

    with (
        patch("app.services.gban_service.settings") as mock_settings,
        patch("app.services.gban_service.aiohttp.ClientSession", side_effect=error),
        patch("app.services.gban_service.asyncio.sleep", new_callable=AsyncMock),
        caplog.at_level(logging.WARNING, logger="app.services.gban_service"),
    ):
        mock_settings.GBAN_LIST_URL = URL

        await GbanService.update_banlist()

    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert warnings
    assert all(record.exc_info is None for record in warnings)


async def test_http_error_is_not_retried(mock_valkey):
    response = FakeResponse(status=500)

    with (
        patch("app.services.gban_service.settings") as mock_settings,
        patch(
            "app.services.gban_service.aiohttp.ClientSession",
            side_effect=session_factory(response),
        ) as mock_session,
        patch("app.services.gban_service.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_settings.GBAN_LIST_URL = URL

        await GbanService.update_banlist()

    assert mock_session.call_count == 1
    mock_valkey.rename.assert_not_awaited()
