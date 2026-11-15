"""Регрессия gban: транзиентные сбои скачивания списка повторяются с backoff."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from app.services.gban_service import GbanService


@pytest.fixture
def mock_valkey():
    with patch("app.services.gban_service.valkey") as m:
        m.delete = AsyncMock()
        m.sadd = AsyncMock()
        m.rename = AsyncMock()
        yield m


def _response(status: int = 200, data=None):
    response = AsyncMock()
    response.status = status
    response.json = AsyncMock(return_value=data)
    response.__aenter__ = AsyncMock(return_value=response)
    response.__aexit__ = AsyncMock(return_value=False)
    return response


def _session(response):
    session = AsyncMock()
    session.get = MagicMock(return_value=response)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


async def test_retries_transient_error_then_succeeds(mock_valkey):
    failing = aiohttp.ClientConnectionError("Connection reset by peer")
    recovering = _session(_response(data=[111, 222]))

    with (
        patch("app.services.gban_service.settings") as mock_settings,
        patch(
            "app.services.gban_service.aiohttp.ClientSession",
            side_effect=[failing, recovering],
        ),
        patch("app.services.gban_service.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        mock_settings.GBAN_LIST_URL = "https://example.com/gban.json"

        await GbanService.update_banlist()

    mock_sleep.assert_awaited_once()
    mock_valkey.rename.assert_awaited_once_with("gban:users:temp", "gban:users")


async def test_gives_up_after_three_attempts(mock_valkey):
    error = aiohttp.ClientConnectionError("Connection reset by peer")

    with (
        patch("app.services.gban_service.settings") as mock_settings,
        patch("app.services.gban_service.aiohttp.ClientSession", side_effect=error) as mock_session,
        patch("app.services.gban_service.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_settings.GBAN_LIST_URL = "https://example.com/gban.json"

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
        mock_settings.GBAN_LIST_URL = "https://example.com/gban.json"

        await GbanService.update_banlist()

    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert warnings
    assert all(record.exc_info is None for record in warnings)


async def test_http_error_is_not_retried(mock_valkey):
    response = _response(status=500)

    with (
        patch("app.services.gban_service.settings") as mock_settings,
        patch("app.services.gban_service.aiohttp.ClientSession", return_value=_session(response)) as mock_session,
        patch("app.services.gban_service.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_settings.GBAN_LIST_URL = "https://example.com/gban.json"

        await GbanService.update_banlist()

    assert mock_session.call_count == 1
    mock_valkey.rename.assert_not_awaited()
