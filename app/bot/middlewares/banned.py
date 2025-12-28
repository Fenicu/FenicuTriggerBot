import contextlib
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import Update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.valkey import valkey
from app.db.models.chat import BannedChat


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
            chat_id = event.callback_query.message.chat.id
        elif event.my_chat_member:
            chat_id = event.my_chat_member.chat.id

        if not chat_id:
            return await handler(event, data)

        # Check cache
        is_banned = await valkey.get(f"banned_chat:{chat_id}")
        if is_banned:
            if event.my_chat_member:
                with contextlib.suppress(Exception):
                    await self.bot.leave_chat(chat_id)
            return None

        # Check DB
        session: AsyncSession = data.get("session")
        if session:
            stmt = select(BannedChat).where(BannedChat.chat_id == chat_id)
            result = await session.execute(stmt)
            banned = result.scalars().first()

            if banned:
                await valkey.set(f"banned_chat:{chat_id}", "1", ex=3600)
                if event.my_chat_member:
                    with contextlib.suppress(Exception):
                        await self.bot.leave_chat(chat_id)
                return None

        return await handler(event, data)
