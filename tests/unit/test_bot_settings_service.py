"""Синхронизация настроек бота через Bot API 10.5 setMySettings."""

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.bot_settings_service import sync_bot_settings


def _bot_info(**overrides):
    values = {
        "can_read_all_group_messages": True,
        "can_join_groups": True,
        "supports_join_request_queries": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _bot(info):
    bot = SimpleNamespace()
    bot.get_me = AsyncMock(return_value=info)
    bot.set_my_settings = AsyncMock(return_value=True)
    return bot


async def test_sets_only_differing_fields():
    bot = _bot(_bot_info(can_read_all_group_messages=False))

    await sync_bot_settings(bot)

    bot.set_my_settings.assert_awaited_once_with(can_read_all_group_messages=True)


async def test_sets_join_request_queries_when_missing():
    bot = _bot(_bot_info(supports_join_request_queries=False))

    await sync_bot_settings(bot)

    bot.set_my_settings.assert_awaited_once_with(supports_join_request_queries=True)


async def test_does_nothing_when_all_settings_match(caplog):
    bot = _bot(_bot_info())

    caplog.set_level(logging.DEBUG, logger="app.services.bot_settings_service")
    await sync_bot_settings(bot)

    bot.set_my_settings.assert_not_awaited()
    assert "up to date" in caplog.text


async def test_get_me_error_is_logged_and_swallowed(caplog):
    bot = _bot(_bot_info())
    bot.get_me.side_effect = RuntimeError("network down")

    with caplog.at_level(logging.WARNING):
        await sync_bot_settings(bot)

    bot.set_my_settings.assert_not_awaited()
    assert "network down" in caplog.text


async def test_set_my_settings_error_is_logged_and_swallowed(caplog):
    bot = _bot(_bot_info(can_join_groups=False))
    bot.set_my_settings.side_effect = RuntimeError("method not found")

    with caplog.at_level(logging.WARNING):
        await sync_bot_settings(bot)

    assert "method not found" in caplog.text


@pytest.mark.parametrize("field", ["can_read_all_group_messages", "can_join_groups", "supports_join_request_queries"])
async def test_each_desired_field_is_enabled(field):
    bot = _bot(_bot_info(**{field: False}))

    await sync_bot_settings(bot)

    bot.set_my_settings.assert_awaited_once_with(**{field: True})
