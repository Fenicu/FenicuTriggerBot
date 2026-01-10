from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from app.db.models.user_chat import UserChat


class UserChatMiddleware(BaseMiddleware):
    """Middleware для обновления связи пользователь-чат."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("user")
        db_chat = data.get("db_chat")
        session = data.get("session")

        if user and db_chat and session:
            # Only for group chats
            if db_chat.type in ("group", "supergroup"):
                user_chat = await session.get(UserChat, (user.id, db_chat.id))
                if not user_chat:
                    user_chat = UserChat(
                        user_id=user.id,
                        chat_id=db_chat.id,
                        is_active=True,
                        is_admin=False,
                    )
                    session.add(user_chat)
                else:
                    if not user_chat.is_active:
                        user_chat.is_active = True
                    user_chat.updated_at = datetime.now().astimezone()

        return await handler(event, data)
