from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, User


class IgnoreMiddleware(BaseMiddleware):
    """Middleware для игнорирования событий от ботов и служебных аккаунтов."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = None
        if isinstance(event, Update) and event.event_type:
            actual_event = getattr(event, event.event_type)
            user = getattr(actual_event, "from_user", None)

        if not user:
            user = data.get("event_from_user")

        if user and user.id == 777000:
            return None

        if user and user.is_bot and user.id != 1087968824:
            return None

        if isinstance(event, Update):
            if event.chat_member:
                new_member = event.chat_member.new_chat_member
                if new_member.user.is_bot:
                    return None

            if event.message and event.message.new_chat_members:
                for member in event.message.new_chat_members:
                    if member.is_bot:
                        return None

        return await handler(event, data)
