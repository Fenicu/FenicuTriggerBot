import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import Update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.valkey import valkey
from app.db.models.chat import BannedChat

CACHE_TTL = 3600


class BannedChatMiddleware(BaseMiddleware):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def __call__(
        self,
        handler: Callable[[Update, dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: dict[str, Any],
    ) -> Any:
        chat_id = None
        if event.message:
            chat_id = event.message.chat.id
        elif event.callback_query:
            if event.callback_query.message:
                chat_id = event.callback_query.message.chat.id
        elif event.my_chat_member:
            chat_id = event.my_chat_member.chat.id

        if not chat_id:
            return await handler(event, data)

        cache_key = f"banned_chat:{chat_id}"
        cached = await valkey.get(cache_key)
        if cached == "1":
            return await self._block(event, chat_id)
        if cached == "0":
            return await handler(event, data)

        session: AsyncSession = data.get("session")
        if session:
            stmt = select(BannedChat.chat_id).where(BannedChat.chat_id == chat_id)
            result = await session.execute(stmt)
            banned = result.scalars().first()

            # Кэшируем и отрицательный результат: обычный чат не ходит в БД на каждом апдейте
            await valkey.set(cache_key, "1" if banned else "0", ex=CACHE_TTL)
            if banned:
                return await self._block(event, chat_id)

        return await handler(event, data)

    async def _block(self, event: Update, chat_id: int) -> None:
        if event.my_chat_member:
            with contextlib.suppress(Exception):
                await self.bot.leave_chat(chat_id)
