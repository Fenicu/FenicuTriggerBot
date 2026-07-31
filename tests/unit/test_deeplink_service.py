"""Tests for app/services/deeplink_service.py — deeplink на карточку чата в Mini App."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services import deeplink_service


@pytest.fixture(autouse=True)
def _reset_module_cache():
    """Сбросить модульный кэш username бота перед каждым тестом."""
    deeplink_service._cache.clear()
    yield
    deeplink_service._cache.clear()


def _mock_get_me(username: str = "test_bot"):
    me = AsyncMock()
    me.username = username
    return AsyncMock(return_value=me)


class TestBuildChatDeeplink:
    async def test_builds_link_with_short_name(self):
        with (
            patch("app.services.deeplink_service.bot") as mock_bot,
            patch.object(deeplink_service.settings, "MINIAPP_SHORT_NAME", "app"),
        ):
            mock_bot.get_me = _mock_get_me("test_bot")

            link = await deeplink_service.build_chat_deeplink(123)

        assert link == "https://t.me/test_bot/app?startapp=chat_123"

    async def test_builds_link_without_short_name_when_empty(self):
        with (
            patch("app.services.deeplink_service.bot") as mock_bot,
            patch.object(deeplink_service.settings, "MINIAPP_SHORT_NAME", ""),
        ):
            mock_bot.get_me = _mock_get_me("test_bot")

            link = await deeplink_service.build_chat_deeplink(123)

        assert link == "https://t.me/test_bot?startapp=chat_123"

    async def test_negative_chat_id_kept_as_is(self):
        with (
            patch("app.services.deeplink_service.bot") as mock_bot,
            patch.object(deeplink_service.settings, "MINIAPP_SHORT_NAME", "app"),
        ):
            mock_bot.get_me = _mock_get_me("test_bot")

            link = await deeplink_service.build_chat_deeplink(-1001381910832)

        assert link == "https://t.me/test_bot/app?startapp=chat_-1001381910832"

    async def test_get_me_error_returns_none(self):
        with patch("app.services.deeplink_service.bot") as mock_bot:
            mock_bot.get_me = AsyncMock(side_effect=RuntimeError("network down"))

            link = await deeplink_service.build_chat_deeplink(123)

        assert link is None

    async def test_get_me_failure_not_cached_retries_next_call(self):
        """Сбой get_me() не должен кэшироваться -- следующий вызов пробует снова (defect #9)."""
        with (
            patch("app.services.deeplink_service.bot") as mock_bot,
            patch.object(deeplink_service.settings, "MINIAPP_SHORT_NAME", "app"),
        ):
            mock_bot.get_me = AsyncMock(side_effect=RuntimeError("network down"))
            first = await deeplink_service.build_chat_deeplink(1)
            assert first is None

            second_get_me = _mock_get_me("test_bot")
            mock_bot.get_me = second_get_me
            second = await deeplink_service.build_chat_deeplink(2)

        assert second == "https://t.me/test_bot/app?startapp=chat_2"
        second_get_me.assert_awaited_once()

    async def test_get_me_called_once_per_process(self):
        with (
            patch("app.services.deeplink_service.bot") as mock_bot,
            patch.object(deeplink_service.settings, "MINIAPP_SHORT_NAME", "app"),
        ):
            mock_bot.get_me = _mock_get_me("test_bot")

            first = await deeplink_service.build_chat_deeplink(1)
            second = await deeplink_service.build_chat_deeplink(2)

        assert first == "https://t.me/test_bot/app?startapp=chat_1"
        assert second == "https://t.me/test_bot/app?startapp=chat_2"
        mock_bot.get_me.assert_awaited_once()
