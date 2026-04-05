import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.instance import bot
from app.core.valkey import valkey
from app.db.models.chat import Chat
from app.db.models.user_chat import UserChat
from app.services.reputation_service import add_message_score, add_reply_score
from app.services.tag_service import update_tag_if_needed

logger = logging.getLogger(__name__)


class ReputationMiddleware(BaseMiddleware):
    """Middleware для начисления очков репутации за сообщения и ответы."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        result = await handler(event, data)

        if not isinstance(event, Message):
            return result

        db_chat: Chat | None = data.get("db_chat")
        session: AsyncSession | None = data.get("session")

        if not db_chat or not session or not db_chat.tags_enabled:
            return result

        if db_chat.type not in ("group", "supergroup"):
            return result

        user_id = event.from_user.id if event.from_user else None
        if not user_id or event.from_user.is_bot:
            return result

        user_chat = await session.get(UserChat, (user_id, db_chat.id))
        if not user_chat:
            return result

        try:
            # Очки за сообщение
            new_level = await add_message_score(session, user_chat, db_chat)
            if new_level is not None:
                await update_tag_if_needed(bot, session, user_chat, db_chat, new_level)

            # Очки за ответ (тому, кому ответили)
            if event.reply_to_message and event.reply_to_message.from_user:
                reply_to_user = event.reply_to_message.from_user
                # Фильтровать ботов и системные аккаунты (777000 — Telegram)
                if not reply_to_user.is_bot and reply_to_user.id != 777000:
                    new_level = await add_reply_score(
                        session, db_chat, user_id, reply_to_user.id, db_chat.id
                    )
                    if new_level is not None:
                        reply_user_chat = await session.get(UserChat, (reply_to_user.id, db_chat.id))
                        if reply_user_chat:
                            await update_tag_if_needed(bot, session, reply_user_chat, db_chat, new_level)

            # Кешировать автора сообщения для обработки реакций
            if event.message_id:
                cache_key = f"msg_author:{db_chat.id}:{event.message_id}"
                await valkey.set(cache_key, str(user_id), ex=604800)  # 7 дней

            await session.commit()
        except Exception:
            logger.exception("Error in reputation middleware")
            await session.rollback()

        return result
