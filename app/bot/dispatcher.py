import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.redis import RedisStorage

from app.bot.handlers import admin, creation, management, matching
from app.bot.middlewares.database import DatabaseMiddleware
from app.bot.middlewares.i18n import I18nMiddleware
from app.core.config import settings
from app.core.i18n import translator_hub
from app.core.valkey import valkey

logger = logging.getLogger(__name__)

session = None
if settings.TELEGRAM_BOT_API_URL:
    session = AiohttpSession(api=TelegramAPIServer.from_base(settings.TELEGRAM_BOT_API_URL))
    logger.info(f"Using local Telegram Bot API server at {settings.TELEGRAM_BOT_API_URL}")
else:
    logger.info("Using default Telegram Bot API server")

bot = Bot(token=settings.BOT_TOKEN, session=session)
storage = RedisStorage(redis=valkey)
dp = Dispatcher(storage=storage)

dp.update.middleware(DatabaseMiddleware())

i18n_middleware = I18nMiddleware(translator_hub=translator_hub, valkey=valkey)
dp.message.outer_middleware(i18n_middleware)
dp.callback_query.outer_middleware(i18n_middleware)

dp.include_router(admin.router)
dp.include_router(creation.router)
dp.include_router(management.router)
dp.include_router(matching.router)
