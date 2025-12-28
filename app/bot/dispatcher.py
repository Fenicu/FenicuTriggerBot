import logging

from aiogram import Dispatcher
from aiogram.fsm.storage.redis import RedisStorage

from app.bot.handlers import admin, creation, management, matching, moderation
from app.bot.instance import bot
from app.bot.middlewares.banned import BannedChatMiddleware
from app.bot.middlewares.database import DatabaseMiddleware
from app.bot.middlewares.i18n import I18nMiddleware
from app.core.i18n import translator_hub
from app.core.valkey import valkey

logger = logging.getLogger(__name__)

storage = RedisStorage(redis=valkey)
dp = Dispatcher(storage=storage)

dp.update.middleware(DatabaseMiddleware())
dp.update.middleware(BannedChatMiddleware(bot))

i18n_middleware = I18nMiddleware(translator_hub=translator_hub, valkey=valkey)
dp.message.outer_middleware(i18n_middleware)
dp.callback_query.outer_middleware(i18n_middleware)

dp.include_router(admin.router)
dp.include_router(creation.router)
dp.include_router(management.router)
dp.include_router(matching.router)
dp.include_router(moderation.router)
