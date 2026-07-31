"""Deeplink на карточку чата в Telegram Mini App — для кнопки в карточке модерации."""

import logging

from app.bot.instance import bot
from app.core.config import settings

logger = logging.getLogger(__name__)

# Username бота меняется не чаще раза в вечность, поэтому успешный get_me() кэшируется
# на весь процесс (см. build_chat_deeplink). Ошибка НЕ кэшируется (defect #9 ревью) --
# иначе один короткий сбой Telegram навсегда отключает кнопку до перезапуска процесса.
# Мутируемый словарь вместо module-level global — правится in-place, без rebind имени.
_cache: dict[str, str | None] = {}
_CACHE_KEY = "bot_username"


async def build_chat_deeplink(chat_id: int) -> str | None:
    """Собрать ссылку на карточку чата в Mini App бота.

    Формат: https://t.me/<bot_username>/<short_name>?startapp=chat_<chat_id>, либо без
    short_name (открывает Main Mini App бота), если settings.MINIAPP_SHORT_NAME пуст.
    При сбое get_me() — залогировать и вернуть None (кнопка не появится), НЕ кэшируя
    ошибку — следующий вызов попробует снова.
    """
    if _CACHE_KEY not in _cache:
        try:
            me = await bot.get_me()
        except Exception as e:
            logger.error("Failed to resolve bot username via get_me: %s", e)
            return None
        _cache[_CACHE_KEY] = me.username

    username = _cache[_CACHE_KEY]
    if username is None:
        return None

    if settings.MINIAPP_SHORT_NAME:
        return f"https://t.me/{username}/{settings.MINIAPP_SHORT_NAME}?startapp=chat_{chat_id}"
    return f"https://t.me/{username}?startapp=chat_{chat_id}"
