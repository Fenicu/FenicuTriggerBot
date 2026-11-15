from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from app.services.daily_stats_service import count_message


class StatsMiddleware(BaseMiddleware):
    """Middleware для сбора статистики."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            # Счётчик копится в Valkey: общая строка DailyStat не блокируется на каждом сообщении
            await count_message()

        return await handler(event, data)
