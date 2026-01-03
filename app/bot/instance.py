import logging

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

from app.core.config import settings

logger = logging.getLogger(__name__)

session = None
if settings.TELEGRAM_BOT_API_URL:
    api_server = TelegramAPIServer(
        base=f"{settings.TELEGRAM_BOT_API_URL}/bot{{token}}/{{method}}",
        file=f"{settings.TELEGRAM_BOT_API_URL}/file/bot{{token}}{{path}}",
    )
    session = AiohttpSession(api=api_server)
    logger.info(f"Using local Telegram Bot API server at {settings.TELEGRAM_BOT_API_URL}")
else:
    logger.info("Using default Telegram Bot API server")

bot = Bot(token=settings.BOT_TOKEN, session=session)
