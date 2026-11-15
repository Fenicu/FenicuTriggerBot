import logging

from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message

logger = logging.getLogger(__name__)

ADMIN_STATUSES = ("administrator", "creator")


def is_anonymous_admin(message: Message) -> bool:
    """Сообщение отправлено анонимным админом (от имени самой группы)."""
    sender_chat = message.sender_chat
    return bool(sender_chat) and sender_chat.id == message.chat.id


async def is_chat_admin(message: Message) -> bool:
    """Автор сообщения -- админ чата. Ошибка getChatMember трактуется как отсутствие прав."""
    if is_anonymous_admin(message):
        return True
    try:
        member = await message.chat.get_member(message.from_user.id)
    except TelegramAPIError as e:
        logger.warning("get_member failed in chat %s: %s", message.chat.id, e)
        return False
    return member.status in ADMIN_STATUSES
