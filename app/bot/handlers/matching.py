import asyncio
import logging

from aiogram import Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.trigger import AccessLevel
from app.services.trigger_service import (
    find_matches,
    get_triggers_by_chat,
    increment_usage,
)

logger = logging.getLogger(__name__)
router = Router()


@router.message()
async def check_triggers(message: Message, session: AsyncSession) -> None:
    """Проверка сообщения на наличие триггеров."""
    if not message.text:
        return

    triggers = await get_triggers_by_chat(session, message.chat.id)
    if not triggers:
        return

    matches = await find_matches(triggers, message.text)
    if matches:
        for i, match in enumerate(matches):
            if i > 0:
                await asyncio.sleep(0.5)

            allowed = True
            if match.access_level == AccessLevel.ADMINS:
                member = await message.chat.get_member(message.from_user.id)
                if member.status not in ("administrator", "creator"):
                    allowed = False
            elif match.access_level == AccessLevel.OWNER:
                member = await message.chat.get_member(message.from_user.id)
                if member.status != "creator":
                    allowed = False

            if allowed:
                try:
                    saved_msg = Message.model_validate(match.content)
                    saved_msg._bot = message.bot

                    await saved_msg.send_copy(chat_id=message.chat.id)

                    await increment_usage(session, match.id)
                except Exception:
                    logger.exception("Error sending trigger message")
