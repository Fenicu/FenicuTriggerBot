"""Хранение gban-списка по bucket'ам в Valkey (реальный тестовый инстанс)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.gban_service import GbanService
from tests.integration.gban_fakes import FakeResponse, session_factory

URL = "https://example.com/gban.json"


@pytest.fixture
async def gban(valkey_client, monkeypatch):
    await valkey_client.flushdb()
    monkeypatch.setattr("app.services.gban_service.valkey", valkey_client)
    return GbanService


async def _load(ids: list[int] | None = None, body: str | None = None) -> None:
    if body is None:
        body = "[" + ",".join(str(i) for i in ids or []) + "]"
    with (
        patch("app.services.gban_service.settings") as mock_settings,
        patch(
            "app.services.gban_service.aiohttp.ClientSession",
            side_effect=session_factory(FakeResponse(body=body)),
        ),
    ):
        mock_settings.GBAN_LIST_URL = URL
        await GbanService.update_banlist()


async def test_membership_after_load(gban, valkey_client):
    await _load([1, 2, 70_000, 70_001])

    assert await gban.is_banned(1) is True
    assert await gban.is_banned(70_000) is True
    assert await gban.is_banned(3) is False
    assert await valkey_client.exists(gban._bucket_key(1)) == 1


async def test_bucket_uses_intset_encoding(gban, valkey_client):
    await _load([1, 2, 3])

    encoding = await valkey_client.execute_command("OBJECT", "ENCODING", gban._bucket_key(1))
    assert encoding == "intset"


async def test_ids_moved_out_of_list_are_unbanned(gban, valkey_client):
    await _load([10, 20, 30, 40])
    assert await gban.is_banned(30) is True

    await _load([10, 20])

    assert await gban.is_banned(10) is True
    assert await gban.is_banned(20) is True
    assert await gban.is_banned(30) is False
    assert await gban.is_banned(40) is False
    assert await valkey_client.exists(gban._bucket_key(30)) == 0
    assert await valkey_client.exists(gban._bucket_key(40)) == 0


async def test_leftover_tmp_buckets_are_cleaned(gban, valkey_client):
    await valkey_client.sadd(gban._temp_bucket_key(5), 5)
    await valkey_client.sadd(gban.TEMP_KEY, 5)

    await _load([1])

    assert await valkey_client.exists(gban._temp_bucket_key(5)) == 0
    assert await valkey_client.exists(gban.TEMP_KEY) == 0


async def test_legacy_keys_removed_after_load(gban, valkey_client):
    await valkey_client.sadd(gban.REDIS_KEY, 42)
    await valkey_client.sadd(gban.TEMP_KEY, 43)

    await _load([1])

    assert await valkey_client.exists(gban.REDIS_KEY) == 0
    assert await valkey_client.exists(gban.TEMP_KEY) == 0


async def test_legacy_fallback_before_first_load(gban, valkey_client):
    await valkey_client.sadd(gban.REDIS_KEY, 42)

    assert await gban.is_banned(42) is True
    assert await gban.is_banned(43) is False
    assert await gban.are_banned([42, 43]) == {42: True, 43: False}
    assert await valkey_client.exists(gban._bucket_key(42 % gban.GBAN_BUCKETS)) == 0

    await _load([1])

    assert await gban.is_banned(42) is False


async def test_are_banned_falls_back_to_legacy_for_misses(gban, valkey_client):
    await _load([1])
    await valkey_client.sadd(gban.REDIS_KEY, 42)

    assert await gban.are_banned([1, 42, 43]) == {1: True, 42: True, 43: False}


async def test_are_banned_matches_is_banned(gban):
    await _load([1, 2, 65_536, 999_999])

    user_ids = [1, 2, 3, 65_536, 65_537, 999_999]
    batch = await gban.are_banned(user_ids)
    singles = {user_id: await gban.is_banned(user_id) for user_id in user_ids}

    assert batch == singles


async def test_are_banned_uses_single_pipeline(gban, valkey_client, monkeypatch):
    await _load([1, 2, 3])

    calls = 0
    original = valkey_client.pipeline

    def counting_pipeline(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(valkey_client, "pipeline", counting_pipeline)

    result = await gban.are_banned([1, 2, 3, 4])

    assert calls == 1
    assert result == {1: True, 2: True, 3: True, 4: False}
