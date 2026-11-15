import logging

from aiogram import Bot
from aiogram.methods.base import TelegramMethod
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import permissions
from app.db.models.chat import Chat
from app.db.models.user_chat import UserChat
from app.services.reputation_service import get_level_name

logger = logging.getLogger(__name__)

# Право, без которого Telegram не даёт ставить теги участникам
TAG_PERMISSION = "can_manage_tags"


class SetChatMemberTag(TelegramMethod[bool]):
    __returning__ = bool
    __api_method__ = "setChatMemberTag"

    chat_id: int | str
    user_id: int
    tag: str


async def update_tag_if_needed(
    bot: Bot,
    session: AsyncSession,
    user_chat: UserChat,
    chat: Chat,
    new_level: int,
) -> None:
    """Обновить тег пользователя при смене уровня (если нет ручного тега).

    Уровень сохраняется только после успешного вызова Telegram API: иначе при
    сбое тег остался бы на старом уровне и больше не пересчитался бы.
    """
    if user_chat.tag_is_manual:
        user_chat.reputation_level = new_level
        await session.flush()
        return

    tag_name = get_level_name(new_level, chat)
    if (tag_name or None) == user_chat.tag:
        user_chat.reputation_level = new_level
        await session.flush()
        return

    success = await _set_chat_member_tag(bot, chat.id, user_chat.user_id, tag_name)
    if not success:
        return

    user_chat.tag = tag_name or None
    user_chat.reputation_level = new_level
    await session.flush()


async def set_manual_tag(
    bot: Bot,
    session: AsyncSession,
    user_chat: UserChat,
    chat_id: int,
    tag: str | None,
) -> bool:
    """Установить ручной тег (от админа)."""
    old_tag = user_chat.tag
    old_is_manual = user_chat.tag_is_manual

    if tag:
        user_chat.tag = tag[:16]
        user_chat.tag_is_manual = True
    else:
        user_chat.tag_is_manual = False
        user_chat.tag = None

    success = await _set_chat_member_tag(bot, chat_id, user_chat.user_id, tag or "")
    if success:
        await session.commit()
    else:
        await session.rollback()
        user_chat.tag = old_tag
        user_chat.tag_is_manual = old_is_manual

    return success


async def clear_manual_tag(
    bot: Bot,
    session: AsyncSession,
    user_chat: UserChat,
    chat: Chat,
) -> bool:
    """Снять ручной тег и вернуть автоматический."""
    old_tag = user_chat.tag
    old_is_manual = user_chat.tag_is_manual

    user_chat.tag_is_manual = False
    auto_tag = get_level_name(user_chat.reputation_level, chat)
    user_chat.tag = auto_tag or None

    success = await _set_chat_member_tag(bot, chat.id, user_chat.user_id, auto_tag)
    if success:
        await session.commit()
    else:
        await session.rollback()
        user_chat.tag = old_tag
        user_chat.tag_is_manual = old_is_manual

    return success


async def tag_calls_blocked(chat_id: int) -> bool:
    """Проверить, закэшировано ли отсутствие права на управление тегами."""
    return await permissions.is_missing(chat_id, TAG_PERMISSION)


async def remember_tag_failure(chat_id: int, error: Exception) -> None:
    """Запомнить отсутствие права на теги, чтобы не звать API на каждое сообщение."""
    permission = permissions.parse_missing_permission(str(error))
    if permission:
        await permissions.record_missing(chat_id, permission)


async def _set_chat_member_tag(bot: Bot, chat_id: int, user_id: int, tag: str) -> bool:
    """Вызвать Telegram API setChatMemberTag."""
    if await tag_calls_blocked(chat_id):
        return False

    try:
        await bot(SetChatMemberTag(chat_id=chat_id, user_id=user_id, tag=tag))
        return True
    except Exception as e:
        await remember_tag_failure(chat_id, e)
        logger.warning(f"Failed to set tag for user {user_id} in chat {chat_id}: {e}")
        return False
