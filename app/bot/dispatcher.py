import logging

from aiogram import Dispatcher, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import ErrorEvent

from app.bot.handlers import (
    admin,
    anime,
    captcha,
    chat_member,
    chat_moderation,
    common,
    creation,
    creation_private,
    management,
    matching,
    moderation,
    reaction,
    reputation,
    src,
    status,
    trust,
    variables,
    welcome,
)
from app.bot.handlers.creation_private import FSM_TTL
from app.bot.instance import bot
from app.bot.middlewares.banned import BannedChatMiddleware
from app.bot.middlewares.chat import ChatMiddleware
from app.bot.middlewares.database import DatabaseMiddleware
from app.bot.middlewares.gban import GbanMiddleware
from app.bot.middlewares.i18n import I18nMiddleware
from app.bot.middlewares.ignore import IgnoreMiddleware
from app.bot.middlewares.permissions import PermissionCheckMiddleware
from app.bot.middlewares.reputation import ReputationMiddleware
from app.bot.middlewares.stats import StatsMiddleware
from app.bot.middlewares.trust import TrustMiddleware
from app.bot.middlewares.user import UserMiddleware
from app.bot.middlewares.user_chat import UserChatMiddleware
from app.core import permissions
from app.core.i18n import translator_hub
from app.core.safe_telegram import is_topic_error
from app.core.valkey import valkey

logger = logging.getLogger(__name__)

storage = RedisStorage(redis=valkey, state_ttl=FSM_TTL, data_ttl=FSM_TTL)
dp = Dispatcher(storage=storage)

dp.update.middleware(DatabaseMiddleware())
dp.message.outer_middleware(StatsMiddleware())
dp.update.middleware(ChatMiddleware())
dp.update.middleware(UserMiddleware())
dp.update.middleware(UserChatMiddleware())
dp.update.middleware(IgnoreMiddleware())
dp.update.middleware(BannedChatMiddleware(bot))
dp.message.outer_middleware(PermissionCheckMiddleware())

i18n_middleware = I18nMiddleware(translator_hub=translator_hub, valkey=valkey)
dp.message.outer_middleware(i18n_middleware)
dp.callback_query.outer_middleware(i18n_middleware)
dp.chat_member.outer_middleware(i18n_middleware)
dp.message_reaction.outer_middleware(i18n_middleware)

dp.message.outer_middleware(GbanMiddleware())

dp.message.middleware(TrustMiddleware())
dp.message.middleware(ReputationMiddleware())

dp.include_router(status.router)
dp.include_router(src.router)
dp.include_router(common.router)
dp.include_router(creation_private.dm_router)
dp.include_router(anime.router)
dp.include_router(admin.router)
dp.include_router(welcome.router)

group_router = Router()
group_router.message.filter(F.chat.type.in_({"group", "supergroup"}))

group_router.include_router(chat_moderation.router)
group_router.include_router(creation.router)
group_router.include_router(creation_private.group_router)
group_router.include_router(management.router)
group_router.include_router(variables.router)
group_router.include_router(reputation.router)
group_router.include_router(matching.router)

dp.include_router(group_router)

dp.include_router(moderation.router)
dp.include_router(captcha.router)
dp.include_router(trust.router)
dp.include_router(chat_member.router)
dp.include_router(reaction.router)


@dp.error()
async def on_telegram_error(event: ErrorEvent) -> bool:
    """Перехват TelegramBadRequest + явное логирование любых других исключений.

    aiogram сам по себе при unhandled exception в handler'е НЕ всегда логирует
    его понятно (зависит от code-path и event-type), и Sentry-SDK auto-instrumentation
    мимо: aiogram оборачивает вызовы handler'ов в свой try/except, exception
    не доходит до asyncio loop exception handler.

    Поэтому: TelegramBadRequest — обрабатываем как раньше (suppress/cache prefer).
    Всё остальное — `logger.exception` (Sentry LoggingIntegration ловит ERROR-уровень
    и шлёт в Glitchtip) и `return False` чтобы aiogram продолжил дефолтную обработку.
    """
    if not isinstance(event.exception, TelegramBadRequest):
        logger.exception(
            "Unhandled handler exception in update %s",
            getattr(event.update, "update_id", "?"),
            exc_info=event.exception,
        )
        return False

    if is_topic_error(event.exception):
        logger.debug("Suppressing topic/thread error: %s", event.exception)
        return True

    error_msg = str(event.exception)
    perm = permissions.parse_missing_permission(error_msg)
    if not perm:
        return False

    chat_id = None
    update = event.update
    if update.message:
        chat_id = update.message.chat.id
    elif update.callback_query and update.callback_query.message:
        chat_id = update.callback_query.message.chat.id
    elif update.my_chat_member:
        chat_id = update.my_chat_member.chat.id
    elif update.chat_member:
        chat_id = update.chat_member.chat.id

    if not chat_id:
        return False

    await permissions.record_missing(chat_id, perm)

    if perm == "can_send_messages" and await permissions.should_leave(chat_id):
        logger.warning("Bot leaving chat %d — can_send_messages missing for 2+ days", chat_id)
        try:
            await bot.leave_chat(chat_id)
        except Exception as e:
            logger.warning("Failed to leave chat %d: %s", chat_id, e)

    return True
