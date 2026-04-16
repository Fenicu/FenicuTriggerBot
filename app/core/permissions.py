"""
Кэш отсутствующих прав бота в чатах.

Когда Telegram возвращает "not enough rights to <action>", парсим конкретное
право и кэшируем его отсутствие в valkey с TTL 1 час. Перед выполнением действия
проверяем кэш — если право закэшировано как отсутствующее, пропускаем API-вызов.

Если can_send_messages отсутствует дольше 2 дней — бот покидает чат.
Кэш сбрасывается по TTL или при получении my_chat_member с новыми правами.
"""

import logging
import time

from app.core.valkey import valkey

logger = logging.getLogger(__name__)

# Маппинг подстрок ошибок Telegram -> имя права
_ERROR_TO_PERMISSION: dict[str, str] = {
    "not enough rights to send text messages": "can_send_messages",
    "not enough rights to send photos": "can_send_messages",
    "not enough rights to send videos": "can_send_messages",
    "not enough rights to send animations": "can_send_messages",
    "not enough rights to send documents": "can_send_messages",
    "not enough rights to send stickers": "can_send_messages",
    "not enough rights to send audio": "can_send_messages",
    "not enough rights to send voice": "can_send_messages",
    "not enough rights to send polls": "can_send_messages",
    "not enough rights to send other messages": "can_send_messages",
    "not enough rights to delete messages": "can_delete_messages",
    "not enough rights to restrict": "can_restrict_members",
    "not enough rights to ban": "can_restrict_members",
    "not enough rights to unban": "can_restrict_members",
    "not enough rights to pin": "can_pin_messages",
    "not enough rights to manage": "can_manage_chat",
    "not enough rights to change": "can_change_info",
    "not enough rights to invite": "can_invite_users",
}

MISSING_KEY = "perm:missing:{chat_id}:{perm}"
FIRST_FAIL_KEY = "perm:first_send_fail:{chat_id}"

CACHE_TTL = 3600  # 1 час
LEAVE_AFTER = 2 * 24 * 3600  # 2 дня
FIRST_FAIL_TTL = 3 * 24 * 3600  # 3 дня (буфер для проверки should_leave)


def parse_missing_permission(error_message: str) -> str | None:
    """Определяет недостающее право по тексту ошибки Telegram."""
    error_lower = error_message.lower()
    for pattern, perm in _ERROR_TO_PERMISSION.items():
        if pattern in error_lower:
            return perm
    return None


async def record_missing(chat_id: int, permission: str) -> None:
    """Записывает отсутствующее право в кэш."""
    key = MISSING_KEY.format(chat_id=chat_id, perm=permission)
    await valkey.set(key, "1", ex=CACHE_TTL)
    logger.info("Cached missing permission %s for chat %d (TTL %ds)", permission, chat_id, CACHE_TTL)

    if permission == "can_send_messages":
        fail_key = FIRST_FAIL_KEY.format(chat_id=chat_id)
        exists = await valkey.exists(fail_key)
        if not exists:
            await valkey.set(fail_key, str(int(time.time())), ex=FIRST_FAIL_TTL)
            logger.info("Started tracking send failure for chat %d (leave after %dd)", chat_id, LEAVE_AFTER // 86400)


async def is_missing(chat_id: int, permission: str) -> bool:
    """Проверяет, закэшировано ли право как отсутствующее."""
    key = MISSING_KEY.format(chat_id=chat_id, perm=permission)
    return await valkey.exists(key) == 1


async def should_leave(chat_id: int) -> bool:
    """Проверяет, нужно ли покинуть чат (can_send_messages отсутствует > 2 дней)."""
    fail_key = FIRST_FAIL_KEY.format(chat_id=chat_id)
    first_fail = await valkey.get(fail_key)
    if not first_fail:
        return False
    elapsed = time.time() - int(first_fail)
    return elapsed >= LEAVE_AFTER


async def clear_for_chat(chat_id: int) -> None:
    """Удаляет все закэшированные отсутствующие права для чата."""
    pattern = MISSING_KEY.format(chat_id=chat_id, perm="*")
    keys = [key async for key in valkey.scan_iter(match=pattern, count=100)]

    fail_key = FIRST_FAIL_KEY.format(chat_id=chat_id)
    keys.append(fail_key)

    if keys:
        await valkey.delete(*keys)
        logger.info("Cleared permission cache for chat %d (%d keys)", chat_id, len(keys))
