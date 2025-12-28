import logging

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

from app.core.config import settings

logger = logging.getLogger(__name__)

session = None
if settings.TELEGRAM_BOT_API_URL:
    session = AiohttpSession(api=TelegramAPIServer.from_base(settings.TELEGRAM_BOT_API_URL))
    logger.info(f"Using local Telegram Bot API server at {settings.TELEGRAM_BOT_API_URL}")
else:
    logger.info("Using default Telegram Bot API server")

bot = Bot(token=settings.BOT_TOKEN, session=session)
