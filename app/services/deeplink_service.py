"""Deeplink на карточку чата в Telegram Mini App — для кнопки в карточке модерации."""

import logging

from app.bot.instance import bot
from app.core.config import settings

logger = logging.getLogger(__name__)

# Username бота меняется не чаще раза в вечность, поэтому get_me() вызывается
# максимум один раз за процесс — кэш переживает и успех, и ошибку (см. build_chat_deeplink).
# Мутируемый словарь вместо module-level global — правится in-place, без rebind имени.
_cache: dict[str, str | None] = {}
_CACHE_KEY = "bot_username"


async def build_chat_deeplink(chat_id: int) -> str | None:
    """Собрать ссылку на карточку чата в Mini App бота.

    Формат: https://t.me/<bot_username>/<short_name>?startapp=chat_<chat_id>, либо без
    short_name (открывает Main Mini App бота), если settings.MINIAPP_SHORT_NAME пуст.
    При сбое get_me() — залогировать и вернуть None, чтобы кнопка просто не появилась.
    """
    if _CACHE_KEY not in _cache:
        try:
            me = await bot.get_me()
            _cache[_CACHE_KEY] = me.username
        except Exception as e:
            logger.error("Failed to resolve bot username via get_me: %s", e)
            _cache[_CACHE_KEY] = None

    username = _cache[_CACHE_KEY]
    if username is None:
        return None

    if settings.MINIAPP_SHORT_NAME:
        return f"https://t.me/{username}/{settings.MINIAPP_SHORT_NAME}?startapp=chat_{chat_id}"
    return f"https://t.me/{username}?startapp=chat_{chat_id}"
