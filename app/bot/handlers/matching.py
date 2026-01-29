import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Router
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time_util import get_timezone
from app.db.models.chat import Chat
from app.db.models.chat_variable import ChatVariable
from app.db.models.trigger import AccessLevel
from app.services.template_service import render_template
from app.services.trigger_service import (
    find_matches,
    get_triggers_by_chat,
    increment_usage,
)

logger = logging.getLogger(__name__)
router = Router()


@router.message()
async def check_triggers(message: Message, session: AsyncSession, db_chat: Chat) -> None:
    """Проверка сообщения на наличие триггеров."""
    if not message.text:
        return

    if not db_chat.module_triggers:
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
                    content = match.content.copy()
                    send_kwargs = {}

                    if match.is_template:
                        send_kwargs["parse_mode"] = "HTML"
                        content.pop("entities", None)
                        content.pop("caption_entities", None)

                        try:
                            tz = ZoneInfo(db_chat.timezone)
                        except Exception:
                            tz = get_timezone()

                        now = datetime.now(tz)
                        user = message.from_user
                        chat = message.chat

                        vars_stmt = select(ChatVariable).where(ChatVariable.chat_id == message.chat.id)
                        vars_result = await session.execute(vars_stmt)
                        chat_vars = {var.key: var.value for var in vars_result.scalars()}

                        context = {
                            "user": {
                                "id": user.id,
                                "username": user.username,
                                "full_name": user.full_name,
                                "first_name": user.first_name,
                                "mention": f'<a href="tg://user?id={user.id}">{user.full_name}</a>',
                            },
                            "chat": {
                                "id": chat.id,
                                "title": chat.title,
                            },
                            "date": now.strftime("%d.%m.%Y"),
                            "time": now.strftime("%H:%M"),
                            "now": now,
                            "vars": chat_vars,
                        }

                        if content.get("text"):
                            try:
                                content["text"] = render_template(content["text"], context)
                            except Exception as e:
                                logger.warning(f"Error rendering template text for trigger {match.id}: {e}")

                        if content.get("caption"):
                            try:
                                content["caption"] = render_template(content["caption"], context)
                            except Exception as e:
                                logger.warning(f"Error rendering template caption for trigger {match.id}: {e}")

                    saved_msg = Message.model_validate(content)
                    saved_msg._bot = message.bot

                    if saved_msg.dice:
                        await message.bot.send_dice(chat_id=message.chat.id, emoji=saved_msg.dice.emoji, **send_kwargs)
                    else:
                        await saved_msg.send_copy(chat_id=message.chat.id, **send_kwargs)

                    await increment_usage(session, match.id)
                except Exception:
                    logger.exception("Error sending trigger message")
