from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Chat, TelegramObject

from app.services.chat_service import get_or_create_chat


class ChatMiddleware(BaseMiddleware):
    """Middleware для автоматической регистрации/обновления чата."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat: Chat | None = data.get("event_chat")
        session = data.get("session")

        if chat and session:
            photo_id = None
            if chat.photo:
                photo_id = chat.photo.big_file_id

            db_chat = await get_or_create_chat(
                session=session,
                chat_id=chat.id,
                title=chat.title,
                username=chat.username,
                type=chat.type,
                description=chat.description,
                invite_link=chat.invite_link,
                photo_id=photo_id,
            )
            data["db_chat"] = db_chat

        return await handler(event, data)
