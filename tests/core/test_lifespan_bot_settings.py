"""Lifespan синхронизирует настройки бота, если это разрешено настройкой."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import app.main as main_module


def _lifespan_deps(order: list[str] | None = None) -> dict[str, object]:
    order = order if order is not None else []

    async def fake_loop(stop_event: asyncio.Event) -> None:
        await stop_event.wait()

    return {
        "valkey": MagicMock(ping=AsyncMock(), aclose=AsyncMock()),
        "engine": MagicMock(dispose=AsyncMock()),
        "storage": MagicMock(ensure_bucket=AsyncMock()),
        "broker": MagicMock(start=AsyncMock(), stop=AsyncMock()),
        "bot": MagicMock(
            set_webhook=AsyncMock(side_effect=lambda **_: order.append("webhook")),
            delete_webhook=AsyncMock(),
        ),
        "set_bot_commands": AsyncMock(),
        "run_flush_loop": fake_loop,
        "flush_daily_stats": AsyncMock(),
    }


async def _run_lifespan(deps: dict[str, object]) -> None:
    with (
        patch.object(main_module, "valkey", deps["valkey"]),
        patch.object(main_module, "engine", deps["engine"]),
        patch.object(main_module, "storage", deps["storage"]),
        patch.object(main_module, "broker", deps["broker"]),
        patch.object(main_module, "bot", deps["bot"]),
        patch.object(main_module, "set_bot_commands", deps["set_bot_commands"]),
        patch.object(main_module, "run_flush_loop", deps["run_flush_loop"]),
        patch.object(main_module, "flush_daily_stats", deps["flush_daily_stats"]),
    ):
        async with main_module.lifespan(main_module.app):
            pass


async def test_sync_runs_after_webhook_when_enabled():
    order: list[str] = []
    deps = _lifespan_deps(order)
    sync = AsyncMock(side_effect=lambda _bot: order.append("sync"))

    with (
        patch.object(main_module, "sync_bot_settings", sync, create=True),
        patch.object(main_module.settings, "BOT_SETTINGS_SYNC_ENABLED", True),
    ):
        await _run_lifespan(deps)

    sync.assert_awaited_once()
    assert order == ["webhook", "sync"]


async def test_sync_is_not_called_when_disabled():
    deps = _lifespan_deps()
    sync = AsyncMock()

    with (
        patch.object(main_module, "sync_bot_settings", sync, create=True),
        patch.object(main_module.settings, "BOT_SETTINGS_SYNC_ENABLED", False),
    ):
        await _run_lifespan(deps)

    sync.assert_not_awaited()
