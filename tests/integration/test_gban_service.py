"""Tests for app/services/gban_service.py — global ban list operations."""

from __future__ import annotations

import tracemalloc
from unittest.mock import AsyncMock, patch

import pytest

from app.services.gban_service import GbanService
from tests.integration.gban_fakes import FakePipeline, FakeResponse, session_factory

URL = "https://example.com/gban.json"


@pytest.fixture
def mock_valkey():
    """Patch valkey used by GbanService."""
    with patch("app.services.gban_service.valkey") as m:
        m.sismember = AsyncMock(return_value=False)
        m.smismember = AsyncMock(return_value=[])
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


async def _run_update(responses, mock_valkey, requests=None):
    with (
        patch("app.services.gban_service.settings") as mock_settings,
        patch(
            "app.services.gban_service.aiohttp.ClientSession",
            side_effect=session_factory(*responses, requests=requests),
        ),
    ):
        mock_settings.GBAN_LIST_URL = URL
        await GbanService.update_banlist()


# ── is_banned ────────────────────────────────────────────────────────────────


class TestIsBanned:
    async def test_returns_true_for_banned_user(self, mock_valkey):
        mock_valkey.sismember = AsyncMock(return_value=True)

        result = await GbanService.is_banned(12345)

        assert result is True

    async def test_returns_false_for_clean_user(self, mock_valkey):
        mock_valkey.sismember = AsyncMock(return_value=False)

        result = await GbanService.is_banned(67890)

        assert result is False


# ── are_banned (batch) ───────────────────────────────────────────────────────


class TestAreBanned:
    async def test_returns_empty_dict_for_empty_input(self, mock_valkey):
        result = await GbanService.are_banned([])

        assert result == {}
        mock_valkey.smismember.assert_not_awaited()

    async def test_matches_individual_is_banned_results(self, mock_valkey):
        """Батч-результат должен совпадать с тем, что дал бы поштучный is_banned для тех же ID."""
        mock_valkey.sismember = AsyncMock(side_effect=[True, False, True])

        result = await GbanService.are_banned([111, 222, 333])

        assert result == {111: True, 222: False, 333: True}

    async def test_single_pipeline_regardless_of_user_count(self, mock_valkey):
        """Пакетная проверка идёт одним pipeline, без N последовательных round-trip."""
        mock_valkey.sismember = AsyncMock(return_value=False)

        await GbanService.are_banned(list(range(10)))

        assert mock_valkey.sismember.await_count == 10
        assert mock_valkey.exists.await_count == 1


# ── update_banlist: потоковый разбор ─────────────────────────────────────────


class TestUpdateBanlistStreaming:
    async def test_skips_when_url_not_set(self, mock_valkey):
        with patch("app.services.gban_service.settings") as mock_settings:
            mock_settings.GBAN_LIST_URL = ""

            await GbanService.update_banlist()

            mock_valkey.delete.assert_not_awaited()

    async def test_handles_non_200_response(self, mock_valkey):
        await _run_update([FakeResponse(status=500)], mock_valkey)

        mock_valkey.sadd.assert_not_awaited()
        mock_valkey.rename.assert_not_awaited()

    async def test_handles_invalid_format(self, mock_valkey):
        await _run_update([FakeResponse(body='{"ids": [1, 2, 3]}')], mock_valkey)

        mock_valkey.sadd.assert_not_awaited()
        mock_valkey.rename.assert_not_awaited()

    async def test_handles_empty_list(self, mock_valkey):
        await _run_update([FakeResponse(body="[]")], mock_valkey)

        mock_valkey.sadd.assert_not_awaited()
        mock_valkey.rename.assert_not_awaited()

    async def test_number_split_across_chunks(self, mock_valkey):
        await _run_update([FakeResponse(chunks=[b"[111,22", b"2,333]"])], mock_valkey)

        members = [uid for call in mock_valkey.sadd.await_args_list for uid in call.args[1:]]
        assert sorted(members) == [111, 222, 333]
        assert mock_valkey.hset.await_args.kwargs["mapping"]["count"] == 3

    async def test_whitespace_and_newlines(self, mock_valkey):
        await _run_update([FakeResponse(body="[\n 111 ,\r\n 222\t,333 \n]")], mock_valkey)

        members = [uid for call in mock_valkey.sadd.await_args_list for uid in call.args[1:]]
        assert sorted(members) == [111, 222, 333]

    async def test_numeric_strings_are_accepted(self, mock_valkey):
        await _run_update([FakeResponse(body='["111", "222"]')], mock_valkey)

        members = [uid for call in mock_valkey.sadd.await_args_list for uid in call.args[1:]]
        assert sorted(members) == [111, 222]

    async def test_large_list_is_written_in_batches_before_full_download(self, mock_valkey):
        ids = list(range(1, 250_001))
        body = "[" + ",".join(str(i) for i in ids) + "]"

        with patch.object(GbanService, "_write_batch", new=AsyncMock(wraps=GbanService._write_batch)) as spy:
            await _run_update([FakeResponse(body=body)], mock_valkey)

        sizes = [len(call.args[0]) for call in spy.await_args_list]
        assert max(sizes) == 200_000
        assert sum(sizes) == 250_000

    async def test_midstream_network_error_keeps_old_list(self, mock_valkey):
        response = FakeResponse(
            chunks=[b"[111,222,"],
            error_after=__import__("aiohttp").ClientPayloadError("connection reset"),
        )

        with patch("app.services.gban_service.asyncio.sleep", new_callable=AsyncMock):
            await _run_update([response, response, response], mock_valkey)

        mock_valkey.rename.assert_not_awaited()
        mock_valkey.hset.assert_not_awaited()


class _DiscardingValkey:
    """Valkey-заглушка, которая ничего не хранит: нужна для замера памяти."""

    async def hgetall(self, _key):
        return {}

    async def hset(self, *_args, **_kwargs):
        return 1

    async def hdel(self, *_args):
        return 0

    async def delete(self, *_keys):
        return 0

    async def unlink(self, *_keys):
        return 0

    async def sadd(self, *_args):
        return 0

    async def rename(self, *_args):
        return True

    async def exists(self, *_keys):
        return 0

    def pipeline(self, **_kwargs):
        return _DiscardingPipeline()


class _DiscardingPipeline:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def __getattr__(self, _name):
        def _noop(*_args, **_kwargs):
            return self

        return _noop

    async def execute(self):
        return []


async def test_ten_million_ids_stream_with_bounded_memory():
    total = 10_000_000
    per_chunk = 10_000

    def chunks():
        yield b"["
        for start in range(1, total + 1, per_chunk):
            end = min(start + per_chunk, total + 1)
            prefix = "" if start == 1 else ","
            yield (prefix + ",".join(str(i) for i in range(start, end))).encode()
        yield b"]"

    response = FakeResponse(chunks=chunks())

    with (
        patch("app.services.gban_service.valkey", _DiscardingValkey()),
        patch("app.services.gban_service.settings") as mock_settings,
        patch(
            "app.services.gban_service.aiohttp.ClientSession",
            side_effect=session_factory(response),
        ),
    ):
        mock_settings.GBAN_LIST_URL = URL
        tracemalloc.start()
        try:
            await GbanService.update_banlist()
            _current, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

    assert peak < 100 * 1024 * 1024
