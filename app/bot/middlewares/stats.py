from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.daily_stat import DailyStat


class StatsMiddleware(BaseMiddleware):
    """Middleware для сбора статистики."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            session: AsyncSession = data["session"]
            today = date.today()

            stmt = (
                insert(DailyStat)
                .values(date=today, messages_count=1)
                .on_conflict_do_update(
                    index_elements=[DailyStat.date],
                    set_={DailyStat.messages_count: DailyStat.messages_count + 1},
                )
            )
            await session.execute(stmt)
            await session.commit()

        return await handler(event, data)
