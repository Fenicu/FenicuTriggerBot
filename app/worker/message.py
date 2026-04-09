import asyncio
import logging

from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from app.bot.instance import bot
from app.core.broker import broker, delayed_exchange

logger = logging.getLogger(__name__)


@broker.subscriber("q.messages.delete", exchange=delayed_exchange)
async def delete_message_task(chat_id: int, message_id: int) -> None:
    """
    Задача для удаления сообщения.
    """
    logger.info(f"Deleting message {message_id} in chat {chat_id}")

    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramRetryAfter as e:
        logger.warning(f"Flood control deleting message {message_id} in {chat_id}, retry in {e.retry_after}s")
        await asyncio.sleep(e.retry_after)
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception as retry_err:
            logger.warning(f"Failed to delete message {message_id} after retry: {retry_err}")
    except TelegramBadRequest as e:
        logger.warning(f"Failed to delete message {message_id} in chat {chat_id}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error deleting message {message_id} in chat {chat_id}: {e}")
