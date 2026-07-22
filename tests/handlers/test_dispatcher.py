"""Тест регистрации guard-bot handler'а (chat_join_request) в диспетчере.

`allowed_updates` для polling/webhook строится из `dp.resolve_used_update_types()` —
без `dp.include_router(join_request.router)` Telegram не пришлёт update'ы этого типа.
"""

import pytest

pytestmark = pytest.mark.asyncio


async def test_chat_join_request_in_resolved_update_types():
    """`chat_join_request` попадает в allowed_updates после регистрации join_request.router."""
    # dm_router — общий singleton, который test_creation_private_integration.py временно
    # цепляет к своему одноразовому Dispatcher'у; отвязываем тем же приёмом, что и там,
    # чтобы реальный app.bot.dispatcher (импортируется здесь единственный раз за сессию
    # тестов — модуль кешируется) мог прицепить его к себе.
    from app.bot.handlers.creation_private import dm_router

    dm_router._parent_router = None

    from app.bot.dispatcher import dp

    assert "chat_join_request" in dp.resolve_used_update_types()
