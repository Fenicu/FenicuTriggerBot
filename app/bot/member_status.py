import logging

from aiogram.exceptions import TelegramAPIError
from aiogram.types import Chat, Message

from app.core.valkey import valkey

logger = logging.getLogger(__name__)

ADMIN_STATUSES = ("administrator", "creator")
MEMBER_STATUS_TTL = 60


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


async def get_cached_member_status(chat: Chat, user_id: int) -> str:
    """Статус участника с коротким кэшем в Valkey -- для горячего пути матчинга."""
    key = f"member_status:{chat.id}:{user_id}"
    try:
        cached = await valkey.get(key)
    except Exception as e:
        logger.warning("Member status cache read failed: %s", e)
        cached = None
    if cached:
        return cached

    member = await chat.get_member(user_id)
    status = str(getattr(member.status, "value", member.status))
    try:
        await valkey.set(key, status, ex=MEMBER_STATUS_TTL)
    except Exception as e:
        logger.warning("Member status cache write failed: %s", e)
    return status
