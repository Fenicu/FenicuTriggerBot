import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User
from fluentogram import TranslatorHub
from redis.asyncio import Redis
from sqlalchemy import select

from app.db.models.chat import Chat

logger = logging.getLogger(__name__)


class I18nMiddleware(BaseMiddleware):
    """Middleware для интернационализации."""

    def __init__(self, translator_hub: TranslatorHub, valkey: Redis) -> None:
        self.translator_hub = translator_hub
        self.valkey = valkey

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        chat = getattr(event, "chat", None)
        if not chat:
            message = getattr(event, "message", None)
            if message:
                chat = getattr(message, "chat", None)

        if not chat:
            logger.debug("Chat not found in event %s", type(event).__name__)

        user: User | None = getattr(event, "from_user", None)

        lang_code = None

        if chat:
            chat_id = chat.id
            lang_code = await self.valkey.get(f"lang:{chat_id}")

            if not lang_code:
                session = data.get("session")
                if session:
                    stmt = select(Chat.language_code).where(Chat.id == chat_id)
                    result = await session.execute(stmt)
                    lang_code = result.scalar_one_or_none()

                    if lang_code:
                        await self.valkey.set(f"lang:{chat_id}", lang_code, ex=3600)

        if not lang_code:
            lang_code = "en" if user and user.language_code == "en" else "ru"

        data["i18n"] = self.translator_hub.get_translator_by_locale(lang_code)

        return await handler(event, data)
