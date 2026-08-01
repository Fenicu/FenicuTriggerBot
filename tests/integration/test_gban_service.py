"""Tests for app/services/gban_service.py — global ban list operations."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.gban_service import GbanService


@pytest.fixture
def mock_valkey():
    """Patch valkey used by GbanService."""
    with patch("app.services.gban_service.valkey") as m:
        m.sismember = AsyncMock(return_value=False)
        m.smismember = AsyncMock(return_value=[])
        m.delete = AsyncMock()
        m.sadd = AsyncMock()
        m.rename = AsyncMock()
        yield m


# ── is_banned ────────────────────────────────────────────────────────────────


class TestIsBanned:
    async def test_returns_true_for_banned_user(self, mock_valkey):
        mock_valkey.sismember = AsyncMock(return_value=True)

        result = await GbanService.is_banned(12345)

        assert result is True
        mock_valkey.sismember.assert_awaited_once_with("gban:users", "12345")

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
        mock_valkey.smismember = AsyncMock(return_value=[1, 0, 1])

        result = await GbanService.are_banned([111, 222, 333])

        assert result == {111: True, 222: False, 333: True}
        mock_valkey.smismember.assert_awaited_once_with("gban:users", ["111", "222", "333"])

    async def test_single_call_regardless_of_user_count(self, mock_valkey):
        """SMISMEMBER одним вызовом вместо N последовательных sismember."""
        mock_valkey.smismember = AsyncMock(return_value=[0] * 10)

        await GbanService.are_banned(list(range(10)))

        assert mock_valkey.smismember.await_count == 1
        mock_valkey.sismember.assert_not_awaited()


# ── update_banlist ───────────────────────────────────────────────────────────


class TestUpdateBanlist:
    async def test_skips_when_url_not_set(self, mock_valkey):
        with patch("app.services.gban_service.settings") as mock_settings:
            mock_settings.GBAN_LIST_URL = ""

            await GbanService.update_banlist()

            mock_valkey.delete.assert_not_awaited()

    async def test_handles_non_200_response(self, mock_valkey):
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.gban_service.settings") as mock_settings,
            patch("app.services.gban_service.aiohttp.ClientSession", return_value=mock_session),
        ):
            mock_settings.GBAN_LIST_URL = "https://example.com/gban.json"

            await GbanService.update_banlist()

            mock_valkey.delete.assert_not_awaited()

    async def test_handles_invalid_json(self, mock_valkey):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(side_effect=ValueError("bad json"))
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.gban_service.settings") as mock_settings,
            patch("app.services.gban_service.aiohttp.ClientSession", return_value=mock_session),
        ):
            mock_settings.GBAN_LIST_URL = "https://example.com/gban.json"

            await GbanService.update_banlist()

            mock_valkey.rename.assert_not_awaited()

    async def test_handles_non_list_format(self, mock_valkey):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"ids": [1, 2, 3]})
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.gban_service.settings") as mock_settings,
            patch("app.services.gban_service.aiohttp.ClientSession", return_value=mock_session),
        ):
            mock_settings.GBAN_LIST_URL = "https://example.com/gban.json"

            await GbanService.update_banlist()

            mock_valkey.rename.assert_not_awaited()

    async def test_handles_empty_list(self, mock_valkey):
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[])
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.gban_service.settings") as mock_settings,
            patch("app.services.gban_service.aiohttp.ClientSession", return_value=mock_session),
        ):
            mock_settings.GBAN_LIST_URL = "https://example.com/gban.json"

            await GbanService.update_banlist()

            mock_valkey.rename.assert_not_awaited()

    async def test_successful_update(self, mock_valkey):
        user_ids = [111, 222, 333]
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=user_ids)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.gban_service.settings") as mock_settings,
            patch("app.services.gban_service.aiohttp.ClientSession", return_value=mock_session),
        ):
            mock_settings.GBAN_LIST_URL = "https://example.com/gban.json"

            await GbanService.update_banlist()

        mock_valkey.delete.assert_awaited_once_with("gban:users:temp")
        mock_valkey.sadd.assert_awaited_once_with("gban:users:temp", "111", "222", "333")
        mock_valkey.rename.assert_awaited_once_with("gban:users:temp", "gban:users")

    async def test_chunked_upload_for_large_lists(self, mock_valkey):
        """Lists > 1000 entries should be uploaded in chunks."""
        user_ids = list(range(2500))
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=user_ids)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.gban_service.settings") as mock_settings,
            patch("app.services.gban_service.aiohttp.ClientSession", return_value=mock_session),
        ):
            mock_settings.GBAN_LIST_URL = "https://example.com/gban.json"

            await GbanService.update_banlist()

        # 2500 / 1000 = 3 chunks
        assert mock_valkey.sadd.await_count == 3
        mock_valkey.rename.assert_awaited_once()

    async def test_handles_network_error(self, mock_valkey):
        """Network errors should be caught and logged, not raised."""
        with (
            patch("app.services.gban_service.settings") as mock_settings,
            patch(
                "app.services.gban_service.aiohttp.ClientSession",
                side_effect=Exception("Connection refused"),
            ),
        ):
            mock_settings.GBAN_LIST_URL = "https://example.com/gban.json"

            # Should not raise
            await GbanService.update_banlist()

            mock_valkey.rename.assert_not_awaited()
