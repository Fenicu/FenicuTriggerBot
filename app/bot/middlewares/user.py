from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, User

from app.services.user_service import get_or_create_user


class UserMiddleware(BaseMiddleware):
    """Middleware для автоматической регистрации/обновления пользователя."""

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

        session = data.get("session")

        if user and session:
            db_user = await get_or_create_user(
                session=session,
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                language_code=user.language_code,
                is_premium=user.is_premium,
            )
            data["user"] = db_user

        return await handler(event, data)
