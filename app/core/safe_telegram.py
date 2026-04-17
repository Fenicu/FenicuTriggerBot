"""
Обёртки над Telegram Bot API с проверкой кэша прав.

Перед вызовом проверяют, не закэшировано ли нужное право как отсутствующее.
При ошибке "not enough rights" — кэшируют и возвращают None/False.
Работают как внутри dispatcher, так и в workers.
"""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatPermissions, Message

from app.core import permissions

logger = logging.getLogger(__name__)


def full_permissions() -> ChatPermissions:
    """Все 15 полей True -- документированный способ Telegram снять все индивидуальные
    ограничения и удалить юзера из списка исключений чата."""
    return ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_edit_tag=True,
        can_change_info=True,
        can_invite_users=True,
        can_pin_messages=True,
        can_manage_topics=True,
    )


def full_restrictions() -> ChatPermissions:
    """Все 15 полей False -- полный мьют. Telegram не импортирует can_send_messages=False
    в остальные send_*, поэтому одного поля мало: юзер сможет слать медиа и стикеры."""
    return ChatPermissions(
        can_send_messages=False,
        can_send_audios=False,
        can_send_documents=False,
        can_send_photos=False,
        can_send_videos=False,
        can_send_video_notes=False,
        can_send_voice_notes=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
        can_edit_tag=False,
        can_change_info=False,
        can_invite_users=False,
        can_pin_messages=False,
        can_manage_topics=False,
    )


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


async def safe_restrict_member(bot: Bot, chat_id: int, user_id: int, **kwargs) -> bool:
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


async def safe_ban_member(bot: Bot, chat_id: int, user_id: int, **kwargs) -> bool:
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


async def safe_unban_member(bot: Bot, chat_id: int, user_id: int, **kwargs) -> bool:
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
