from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from fluentogram import TranslatorRunner
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.trust_history import ChatTrustHistory
from app.services.chat_service import get_or_create_chat
from app.services.user_service import get_or_create_user


class TrustMiddleware(BaseMiddleware):
    """
    Middleware для управления доверием.
    1. Получает/создает пользователя в БД.
    2. Проверяет, является ли пользователь доверенным.
    3. Если доверенный пользователь пишет в недоверенный чат -> чат становится доверенным.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        session: AsyncSession = data["session"]
        user = event.from_user
        chat = event.chat

        if not user:
            return await handler(event, data)

        db_user = await get_or_create_user(
            session,
            user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
        )
        data["user"] = db_user

        if chat.type in ("group", "supergroup"):
            db_chat = await get_or_create_chat(session, chat.id)

            if not db_chat.is_trusted and db_user.is_trusted:
                db_chat.is_trusted = True
                session.add(db_chat)

                history = ChatTrustHistory(
                    chat_id=chat.id,
                    user_id=user.id,
                    event_type="granted",
                )
                session.add(history)

                await session.commit()

                i18n: TranslatorRunner = data.get("i18n")
                if i18n:
                    user_name = user.username or user.full_name
                    await event.answer(i18n.get("chat-became-trusted", user=user_name))

        return await handler(event, data)
