import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject
from fluentogram import TranslatorRunner

from app.services.gban_service import GbanService

logger = logging.getLogger(__name__)


class GbanMiddleware(BaseMiddleware):
    """Middleware для проверки глобального бана."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)

        chat = event.chat
        if chat.type not in ("group", "supergroup"):
            return await handler(event, data)

        db_chat = data.get("db_chat")
        if not db_chat or not db_chat.gban_enabled:
            return await handler(event, data)

        user = event.from_user
        if not user:
            return await handler(event, data)

        if event.new_chat_members:
            return await handler(event, data)

        if await GbanService.is_banned(user.id):
            i18n: TranslatorRunner = data.get("i18n")

            try:
                await event.reply(
                    text=i18n.gban.user.warning(user=user.mention_html()),
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text=i18n.btn.close(),
                                    callback_data="delete_this",
                                )
                            ]
                        ]
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to send gban warning: {e}")

        return await handler(event, data)
