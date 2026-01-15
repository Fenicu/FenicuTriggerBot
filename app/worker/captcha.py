import logging
from datetime import datetime, timedelta

from aiogram.exceptions import TelegramBadRequest
from app.bot.instance import bot
from app.core.broker import broker
from app.core.database import engine
from app.core.i18n import translator_hub
from app.core.valkey import valkey
from app.db.models.captcha_session import ChatCaptchaSession
from faststream.rabbit import RabbitExchange
from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)
async_session = async_sessionmaker(engine, expire_on_commit=False)

delayed_exchange = RabbitExchange(
    name="delayed_exchange",
    type="x-delayed-message",
    arguments={"x-delayed-type": "direct"},
)


@broker.subscriber("q.captcha.kick", exchange=delayed_exchange)
async def kick_unverified_user(chat_id: int, user_id: int, session_id: int) -> None:
    """
    Задача для кика пользователя, не прошедшего капчу.
    """
    logger.info(f"Checking captcha status for user {user_id} in chat {chat_id}")

    async with async_session() as session:
        captcha_session = await session.get(ChatCaptchaSession, session_id)

        if not captcha_session:
            logger.warning(f"Captcha session {session_id} not found")
            return

        if captcha_session.is_completed:
            logger.info(f"User {user_id} already verified")
            return

        if captcha_session.expires_at > datetime.now().astimezone():
            logger.info(f"Captcha session {session_id} not yet expired")
            return

        try:
            await bot.ban_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                until_date=timedelta(minutes=1),
            )
            await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)

            try:
                lang_code = await valkey.get(f"lang:{chat_id}")
                i18n = translator_hub.get_translator_by_locale(lang_code or "ru")

                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=captcha_session.message_id,
                    text=i18n.get("captcha-timeout-kick"),
                )
            except TelegramBadRequest as e:
                logger.warning(f"Failed to edit message: {e}")

        except Exception as e:
            logger.error(f"Failed to kick user {user_id}: {e}")
