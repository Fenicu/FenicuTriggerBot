"""Lifespan запускает фоновый сброс статистики и делает финальный сброс при остановке."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import app.main as main_module


async def test_lifespan_runs_flusher_and_flushes_on_shutdown():
    started = asyncio.Event()
    cancelled = False

    async def fake_loop() -> None:
        nonlocal cancelled
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled = True
            raise

    final_flush = AsyncMock()
    order: list[str] = []
    final_flush.side_effect = lambda: order.append("flush")
    valkey = MagicMock(ping=AsyncMock(), aclose=AsyncMock(side_effect=lambda: order.append("valkey_closed")))
    engine = MagicMock(dispose=AsyncMock(side_effect=lambda: order.append("engine_disposed")))

    with (
        patch.object(main_module, "valkey", valkey),
        patch.object(main_module, "engine", engine),
        patch.object(main_module, "storage", MagicMock(ensure_bucket=AsyncMock())),
        patch.object(main_module, "broker", MagicMock(start=AsyncMock(), stop=AsyncMock())),
        patch.object(main_module, "bot", MagicMock(set_webhook=AsyncMock(), delete_webhook=AsyncMock())),
        patch.object(main_module, "set_bot_commands", AsyncMock()),
        patch.object(main_module, "run_flush_loop", fake_loop, create=True),
        patch.object(main_module, "flush_daily_stats", final_flush, create=True),
    ):
        async with main_module.lifespan(main_module.app):
            await asyncio.wait_for(started.wait(), timeout=1)
            final_flush.assert_not_awaited()

    assert cancelled
    final_flush.assert_awaited_once()
    assert order == ["flush", "valkey_closed", "engine_disposed"]


async def test_lifespan_shutdown_survives_final_flush_error():
    async def fake_loop() -> None:
        await asyncio.Event().wait()

    engine = MagicMock(dispose=AsyncMock())

    with (
        patch.object(main_module, "valkey", MagicMock(ping=AsyncMock(), aclose=AsyncMock())),
        patch.object(main_module, "engine", engine),
        patch.object(main_module, "storage", MagicMock(ensure_bucket=AsyncMock())),
        patch.object(main_module, "broker", MagicMock(start=AsyncMock(), stop=AsyncMock())),
        patch.object(main_module, "bot", MagicMock(set_webhook=AsyncMock(), delete_webhook=AsyncMock())),
        patch.object(main_module, "set_bot_commands", AsyncMock()),
        patch.object(main_module, "run_flush_loop", fake_loop, create=True),
        patch.object(main_module, "flush_daily_stats", AsyncMock(side_effect=RuntimeError("db down")), create=True),
    ):
        async with main_module.lifespan(main_module.app):
            pass

    engine.dispose.assert_awaited_once()
