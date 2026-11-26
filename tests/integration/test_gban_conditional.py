"""Условная загрузка gban-списка: ETag / Last-Modified и 304 Not Modified."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.gban_service import GbanService
from tests.integration.gban_fakes import FakePipeline, FakeResponse, session_factory

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


async def _update(mock_valkey, responses, requests=None):
    with (
        patch("app.services.gban_service.settings") as mock_settings,
        patch(
            "app.services.gban_service.aiohttp.ClientSession",
            side_effect=session_factory(*responses, requests=requests),
        ),
    ):
        mock_settings.GBAN_LIST_URL = URL
        await GbanService.update_banlist()


async def test_304_does_not_write_anything(mock_valkey):
    mock_valkey.hgetall = AsyncMock(return_value={"etag": '"v1"', "last_modified": "Wed, 01 Jan 2026 00:00:00 GMT"})

    await _update(mock_valkey, [FakeResponse(status=304)])

    mock_valkey.hset.assert_not_awaited()
    mock_valkey.hdel.assert_not_awaited()
    mock_valkey.sadd.assert_not_awaited()
    mock_valkey.rename.assert_not_awaited()
    mock_valkey.delete.assert_not_awaited()
    mock_valkey.unlink.assert_not_awaited()


async def test_sends_conditional_headers(mock_valkey):
    mock_valkey.hgetall = AsyncMock(return_value={"etag": '"v1"', "last_modified": "Wed, 01 Jan 2026 00:00:00 GMT"})
    requests: list[dict[str, str] | None] = []

    await _update(mock_valkey, [FakeResponse(status=304)], requests=requests)

    assert requests[0] == {
        "If-None-Match": '"v1"',
        "If-Modified-Since": "Wed, 01 Jan 2026 00:00:00 GMT",
    }


async def test_200_stores_validators(mock_valkey):
    response = FakeResponse(
        body="[111, 222]",
        headers={"ETag": '"v2"', "Last-Modified": "Thu, 02 Jan 2026 00:00:00 GMT"},
    )

    await _update(mock_valkey, [response])

    mapping = mock_valkey.hset.await_args.kwargs["mapping"]
    assert mapping["count"] == 2
    assert mapping["etag"] == '"v2"'
    assert mapping["last_modified"] == "Thu, 02 Jan 2026 00:00:00 GMT"


async def test_200_without_validators_clears_old_ones(mock_valkey):
    mock_valkey.hgetall = AsyncMock(return_value={"etag": '"old"', "last_modified": "old"})

    await _update(mock_valkey, [FakeResponse(body="[111]")])

    mapping = mock_valkey.hset.await_args.kwargs["mapping"]
    assert "etag" not in mapping
    assert "last_modified" not in mapping
    assert {call.args[1] for call in mock_valkey.hdel.await_args_list} == {"etag", "last_modified"}
