from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Chat
from app.db.models.user import User
from app.db.models.user_chat import UserChat


class UserChatMiddleware(BaseMiddleware):
    """Middleware для обновления связи пользователь-чат."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User = data.get("user")
        db_chat: Chat = data.get("db_chat")
        session: AsyncSession = data.get("session")

        if user and db_chat and session and db_chat.type in ("group", "supergroup"):
            stmt = (
                insert(UserChat)
                .values(user_id=user.id, chat_id=db_chat.id, is_active=True, is_admin=False)
                .on_conflict_do_update(
                    index_elements=[UserChat.user_id, UserChat.chat_id],
                    set_={"is_active": True, "updated_at": func.now()},
                )
            )
            await session.execute(stmt)
            await session.commit()

        return await handler(event, data)
