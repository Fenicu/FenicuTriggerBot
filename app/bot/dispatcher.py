import logging

from aiogram import Dispatcher, F, Router
from aiogram.fsm.storage.redis import RedisStorage

from app.bot.handlers import (
    admin,
    anime,
    chat_member,
    chat_moderation,
    common,
    creation,
    management,
    matching,
    moderation,
    status,
    trust,
)
from app.bot.instance import bot
from app.bot.middlewares.banned import BannedChatMiddleware
from app.bot.middlewares.chat import ChatMiddleware
from app.bot.middlewares.database import DatabaseMiddleware
from app.bot.middlewares.i18n import I18nMiddleware
from app.bot.middlewares.stats import StatsMiddleware
from app.bot.middlewares.trust import TrustMiddleware
from app.bot.middlewares.user import UserMiddleware
from app.bot.middlewares.user_chat import UserChatMiddleware
from app.core.i18n import translator_hub
from app.core.valkey import valkey

logger = logging.getLogger(__name__)

storage = RedisStorage(redis=valkey)
dp = Dispatcher(storage=storage)

dp.update.middleware(DatabaseMiddleware())
dp.update.middleware(StatsMiddleware())
dp.update.middleware(ChatMiddleware())
dp.update.middleware(UserMiddleware())
dp.update.middleware(UserChatMiddleware())
dp.update.middleware(BannedChatMiddleware(bot))

i18n_middleware = I18nMiddleware(translator_hub=translator_hub, valkey=valkey)
dp.message.outer_middleware(i18n_middleware)
dp.callback_query.outer_middleware(i18n_middleware)

dp.message.middleware(TrustMiddleware())

dp.include_router(status.router)
dp.include_router(common.router)
dp.include_router(anime.router)
dp.include_router(admin.router)

group_router = Router()
group_router.message.filter(F.chat.type.in_({"group", "supergroup"}))

group_router.include_router(chat_moderation.router)
group_router.include_router(creation.router)
group_router.include_router(management.router)
group_router.include_router(matching.router)

dp.include_router(group_router)

dp.include_router(moderation.router)
dp.include_router(trust.router)
dp.include_router(chat_member.router)
