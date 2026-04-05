import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.instance import bot
from app.core.database import engine
from app.db.models.chat import Chat
from app.db.models.user_chat import UserChat
from app.services.reputation_service import calculate_level, get_level_name, get_thresholds
from app.services.tag_service import SetChatMemberTag

logger = logging.getLogger(__name__)

async_session = async_sessionmaker(engine, expire_on_commit=False)


async def recalculate_chat_tags(chat_id: int) -> None:
    """Пересчитать уровни и теги всех пользователей чата."""
    async with async_session() as session:
        chat = await session.get(Chat, chat_id)
        if not chat or not chat.tags_enabled:
            return

        thresholds = get_thresholds(chat)

        # Get all active users in this chat
        stmt = select(UserChat).where(
            UserChat.chat_id == chat_id,
            UserChat.is_active.is_(True),
        )
        result = await session.execute(stmt)
        user_chats = result.scalars().all()

        updated = 0
        for user_chat in user_chats:
            if user_chat.tag_is_manual:
                continue

            new_level = calculate_level(user_chat.reputation_score, thresholds)
            new_tag = get_level_name(new_level, chat)

            if new_level == user_chat.reputation_level and new_tag == user_chat.tag:
                continue

            user_chat.reputation_level = new_level
            user_chat.tag = new_tag or None

            # Call Telegram API with rate limiting
            try:
                await bot(SetChatMemberTag(
                    chat_id=chat_id,
                    user_id=user_chat.user_id,
                    tag=new_tag or "",
                ))
                updated += 1
            except Exception as e:
                logger.warning(
                    "Failed to update tag for user %d in chat %d: %s",
                    user_chat.user_id,
                    chat_id,
                    e,
                )

            # Rate limit: 1 request per 100ms to avoid hitting Telegram limits
            await asyncio.sleep(0.1)

        await session.commit()
        logger.info(
            "Recalculated tags for chat %d: %d/%d users updated",
            chat_id,
            updated,
            len(user_chats),
        )
