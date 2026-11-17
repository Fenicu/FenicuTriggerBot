import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, Update

from app.core import permissions
from app.core.broker import schedule_autodelete

logger = logging.getLogger(__name__)


class ServiceAutodeleteMiddleware(BaseMiddleware):
    """Планирует автоудаление сервисных сообщений о входе и выходе участников.

    Стоит до IgnoreMiddleware: служебные сообщения о снятии участника нашим ботом
    приходят с `from_user`-ботом, а о входе бота -- с ботом среди новых участников,
    и дальше по цепочке такие апдейты отбрасываются.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            await self._schedule(event, data)
        except Exception as e:
            logger.warning("Failed to schedule service message autodelete: %s", e)
        return await handler(event, data)

    @staticmethod
    async def _schedule(event: TelegramObject, data: dict[str, Any]) -> None:
        if not isinstance(event, Update):
            return
        message: Message | None = event.message
        if message is None:
            return
        if message.chat.type not in ("group", "supergroup"):
            return

        db_chat = data.get("db_chat")
        if db_chat is None:
            return

        # Оба признака одновременно -- только теория; удаляем сообщение один раз
        if message.new_chat_members:
            msg_type = "service_join"
        elif message.left_chat_member:
            msg_type = "service_leave"
        else:
            return

        settings = db_chat.autodelete_settings
        config = (settings or {}).get(msg_type)
        if not config or not config.get("enabled"):
            return
        if await permissions.is_missing(message.chat.id, "can_delete_messages"):
            return
        await schedule_autodelete(message.chat.id, message.message_id, settings, msg_type)
