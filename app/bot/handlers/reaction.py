import logging

from aiogram import Router
from aiogram.types import MessageReactionUpdated
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.instance import bot
from app.core.valkey import valkey
from app.db.models.chat import Chat
from app.db.models.user_chat import UserChat
from app.services.reputation_service import add_reaction_score
from app.services.tag_service import update_tag_if_needed

logger = logging.getLogger(__name__)

router = Router()


@router.message_reaction()
async def on_message_reaction(event: MessageReactionUpdated, session: AsyncSession) -> None:
    """Обработчик реакций на сообщения."""
    chat_id = event.chat.id

    if event.chat.type not in ("group", "supergroup"):
        return

    from_user = event.user
    if not from_user or from_user.is_bot or from_user.id == 777000:
        return

    # Only award points for truly new reactions (not changes/removals)
    old_count = len(event.old_reaction) if event.old_reaction else 0
    new_count = len(event.new_reaction) if event.new_reaction else 0
    if new_count <= old_count:
        return

    db_chat = await session.get(Chat, chat_id)
    if not db_chat or not db_chat.tags_enabled:
        return

    # Get message author from Valkey cache
    cache_key = f"msg_author:{chat_id}:{event.message_id}"
    to_user_id_raw = await valkey.get(cache_key)

    if not to_user_id_raw:
        return

    to_user_id = int(to_user_id_raw)

    # Фильтровать системные аккаунты
    if to_user_id == 777000:
        return

    try:
        new_level = await add_reaction_score(session, db_chat, from_user.id, to_user_id, chat_id)

        if new_level is not None:
            user_chat = await session.get(UserChat, (to_user_id, chat_id))
            if user_chat:
                await update_tag_if_needed(bot, session, user_chat, db_chat, new_level)

        await session.commit()
    except Exception:
        logger.exception("Error in reaction handler")
        await session.rollback()
