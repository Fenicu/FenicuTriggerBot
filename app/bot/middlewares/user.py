from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from app.services.user_service import get_or_create_user


class UserMiddleware(BaseMiddleware):
    """Middleware для автоматической регистрации/обновления пользователя."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        session = data.get("session")

        if user and session:
            db_user = await get_or_create_user(
                session=session,
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
            )
            data["user"] = db_user

        return await handler(event, data)
