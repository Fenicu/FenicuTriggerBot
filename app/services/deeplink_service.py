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


def _web_chat_url(chat_id: int) -> str:
    """Прямая веб-ссылка на карточку чата (HashRouter фронта)."""
    base = settings.WEBAPP_URL.rstrip("/")
    prefix = settings.URL_PREFIX.rstrip("/")
    return f"{base}{prefix}/webapp/#/chats/{chat_id}"


async def build_chat_deeplink(chat_id: int) -> str | None:
    """Собрать ссылку на карточку чата для кнопки в карточке модерации.

    Пока MINIAPP_SHORT_NAME не задан, отдаём прямую веб-ссылку: ссылка вида
    https://t.me/<bot>?startapp=... работает ТОЛЬКО когда у бота настроен Main Mini App
    (getMe.has_main_web_app), иначе она просто открывает чат с ботом. Как только Mini App
    заведён в BotFather и short_name прописан в окружении, кнопка сама становится
    deeplink'ом: https://t.me/<bot>/<short_name>?startapp=chat_<chat_id>.
    При сбое get_me() — веб-ссылка (она не требует username), ошибка НЕ кэшируется.
    """
    if not settings.MINIAPP_SHORT_NAME:
        return _web_chat_url(chat_id)

    if _CACHE_KEY not in _cache:
        try:
            me = await bot.get_me()
        except Exception as e:
            logger.error("Failed to resolve bot username via get_me: %s", e)
            return _web_chat_url(chat_id)
        _cache[_CACHE_KEY] = me.username

    username = _cache[_CACHE_KEY]
    if username is None:
        return _web_chat_url(chat_id)

    return f"https://t.me/{username}/{settings.MINIAPP_SHORT_NAME}?startapp=chat_{chat_id}"
