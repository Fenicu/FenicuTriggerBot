import logging

import aiohttp

from app.core.config import settings
from app.core.valkey import valkey

logger = logging.getLogger(__name__)


class GbanService:
    REDIS_KEY = "gban:users"
    TEMP_KEY = "gban:users:temp"

    @classmethod
    async def is_banned(cls, user_id: int) -> bool:
        """Проверяет, находится ли пользователь в глобальном бан-листе."""
        return bool(await valkey.sismember(cls.REDIS_KEY, str(user_id)))

    @classmethod
    async def update_banlist(cls) -> None:
        """Обновляет глобальный бан-лист из внешнего источника."""
        url = settings.GBAN_LIST_URL
        if not url:
            logger.warning("GBAN_LIST_URL is not set. Skipping update.")
            return

        try:
            async with aiohttp.ClientSession() as session, session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch gban list: {response.status}")
                    return

                try:
                    data = await response.json()
                except Exception:
                    logger.error("Failed to parse gban list JSON")
                    return

                ids: list[str] = []
                if isinstance(data, list):
                    ids = [str(x) for x in data]
                else:
                    logger.error(f"Unknown gban list format: {type(data)}")
                    return

                if not ids:
                    logger.info("Gban list is empty.")
                    return

                await valkey.delete(cls.TEMP_KEY)

                chunk_size = 1000
                for i in range(0, len(ids), chunk_size):
                    chunk = ids[i : i + chunk_size]
                    await valkey.sadd(cls.TEMP_KEY, *chunk)

                await valkey.rename(cls.TEMP_KEY, cls.REDIS_KEY)

                logger.info(f"Updated gban list with {len(ids)} users.")

        except Exception as e:
            logger.exception(f"Error updating gban list: {e}")
