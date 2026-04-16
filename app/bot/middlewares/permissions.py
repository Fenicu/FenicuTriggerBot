"""
Middleware для пропуска обработки сообщений в чатах,
где у бота нет права отправлять сообщения.

Проверяет кэш прав перед передачей апдейта в хэндлер.
Если can_send_messages закэшировано как отсутствующее — обработка пропускается.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message

from app.core import permissions

logger = logging.getLogger(__name__)


class PermissionCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        chat_id = event.chat.id

        if event.chat.type in ("group", "supergroup") and await permissions.is_missing(chat_id, "can_send_messages"):
            logger.debug("Skipping message handler for chat %d (can_send_messages missing)", chat_id)
            return None

        return await handler(event, data)
