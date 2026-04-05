import logging

from aiogram import Bot
from aiogram.methods.base import TelegramMethod
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Chat
from app.db.models.user_chat import UserChat
from app.services.reputation_service import get_level_name

logger = logging.getLogger(__name__)


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
    """Обновить тег пользователя при смене уровня (если нет ручного тега)."""
    if user_chat.tag_is_manual:
        return

    tag_name = get_level_name(new_level, chat)
    if tag_name == user_chat.tag:
        return

    old_tag = user_chat.tag
    user_chat.tag = tag_name or None

    success = await _set_chat_member_tag(bot, chat.id, user_chat.user_id, tag_name)
    if success:
        await session.flush()
    else:
        user_chat.tag = old_tag


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


async def _set_chat_member_tag(bot: Bot, chat_id: int, user_id: int, tag: str) -> bool:
    """Вызвать Telegram API setChatMemberTag."""
    try:
        await bot(SetChatMemberTag(chat_id=chat_id, user_id=user_id, tag=tag))
        return True
    except Exception:
        logger.exception(f"Failed to set tag for user {user_id} in chat {chat_id}")
        return False
