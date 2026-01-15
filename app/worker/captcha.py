import logging
from datetime import datetime, timedelta

from aiogram.exceptions import TelegramBadRequest
from app.bot.instance import bot
from app.core.broker import broker
from app.core.database import engine
from app.db.models.captcha_session import ChatCaptchaSession
from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)
async_session = async_sessionmaker(engine, expire_on_commit=False)


@broker.subscriber("q.captcha.kick")
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

        # Если время еще не вышло, но задача запустилась (например, при рестарте),
        # проверяем expires_at.
        if captcha_session.expires_at > datetime.now():
            logger.info(f"Captcha session {session_id} not yet expired")
            return

        # Кикаем пользователя
        try:
            # Баним пользователя (кик)
            # until_date должен быть > 30 секунд от текущего времени, но < 366 дней
            # Чтобы просто кикнуть и дать возможность вернуться, баним и сразу разбаниваем
            await bot.ban_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                until_date=timedelta(minutes=1),  # Формально баним на минуту
            )
            # Сразу разбаниваем, чтобы удалить из черного списка (если нужно просто кикнуть)
            await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)

            # Обновляем сообщение
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=captcha_session.message_id,
                    text="❌ Время вышло. Пользователь был исключен.",
                )
            except TelegramBadRequest as e:
                # Сообщение могло быть удалено или изменено
                logger.warning(f"Failed to edit message: {e}")

        except Exception as e:
            logger.error(f"Failed to kick user {user_id}: {e}")
