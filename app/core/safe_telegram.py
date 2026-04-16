"""
Обёртки над Telegram Bot API с проверкой кэша прав.

Перед вызовом проверяют, не закэшировано ли нужное право как отсутствующее.
При ошибке "not enough rights" — кэшируют и возвращают None/False.
Работают как внутри dispatcher, так и в workers.
"""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from app.core import permissions

logger = logging.getLogger(__name__)


async def safe_send_message(bot: Bot, chat_id: int, **kwargs) -> Message | None:
    """Отправить сообщение. Возвращает Message или None если нет прав."""
    if await permissions.is_missing(chat_id, "can_send_messages"):
        return None
    try:
        return await bot.send_message(chat_id, **kwargs)
    except TelegramBadRequest as e:
        perm = permissions.parse_missing_permission(str(e))
        if perm:
            await permissions.record_missing(chat_id, perm)
            return None
        raise


async def safe_delete_message(bot: Bot, chat_id: int, message_id: int) -> bool:
    """Удалить сообщение. Возвращает True если удалено, False если нет прав."""
    if await permissions.is_missing(chat_id, "can_delete_messages"):
        return False
    try:
        await bot.delete_message(chat_id, message_id)
        return True
    except TelegramBadRequest as e:
        perm = permissions.parse_missing_permission(str(e))
        if perm:
            await permissions.record_missing(chat_id, perm)
            return False
        raise


async def safe_restrict_member(
    bot: Bot, chat_id: int, user_id: int, **kwargs
) -> bool:
    """Ограничить пользователя. Возвращает True если успешно."""
    if await permissions.is_missing(chat_id, "can_restrict_members"):
        return False
    try:
        await bot.restrict_chat_member(chat_id, user_id, **kwargs)
        return True
    except TelegramBadRequest as e:
        perm = permissions.parse_missing_permission(str(e))
        if perm:
            await permissions.record_missing(chat_id, perm)
            return False
        raise


async def safe_ban_member(
    bot: Bot, chat_id: int, user_id: int, **kwargs
) -> bool:
    """Забанить пользователя. Возвращает True если успешно."""
    if await permissions.is_missing(chat_id, "can_restrict_members"):
        return False
    try:
        await bot.ban_chat_member(chat_id, user_id, **kwargs)
        return True
    except TelegramBadRequest as e:
        perm = permissions.parse_missing_permission(str(e))
        if perm:
            await permissions.record_missing(chat_id, perm)
            return False
        raise


async def safe_unban_member(
    bot: Bot, chat_id: int, user_id: int, **kwargs
) -> bool:
    """Разбанить пользователя. Возвращает True если успешно."""
    if await permissions.is_missing(chat_id, "can_restrict_members"):
        return False
    try:
        await bot.unban_chat_member(chat_id, user_id, **kwargs)
        return True
    except TelegramBadRequest as e:
        perm = permissions.parse_missing_permission(str(e))
        if perm:
            await permissions.record_missing(chat_id, perm)
            return False
        raise
