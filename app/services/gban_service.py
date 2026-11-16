import asyncio
import logging
from typing import Any

import aiohttp

from app.core.config import settings
from app.core.valkey import valkey

logger = logging.getLogger(__name__)

# Сколько раз пробовать скачать список и пауза между попытками (секунды)
_FETCH_ATTEMPTS = 3
_FETCH_BACKOFF = 1.0

# Ошибки сети, при которых имеет смысл повторить запрос
_TRANSIENT_ERRORS = (aiohttp.ClientError, asyncio.TimeoutError, OSError)


class GbanService:
    REDIS_KEY = "gban:users"
    TEMP_KEY = "gban:users:temp"

    @classmethod
    async def is_banned(cls, user_id: int) -> bool:
        """Проверяет, находится ли пользователь в глобальном бан-листе."""
        return bool(await valkey.sismember(cls.REDIS_KEY, str(user_id)))

    @classmethod
    async def are_banned(cls, user_ids: list[int]) -> dict[int, bool]:
        """Проверяет несколько пользователей одним запросом (SMISMEMBER).

        Заменяет N последовательных sismember одним round-trip -- иначе список
        из 100 пользователей на странице даёт 100 обращений к Valkey (см. defect #3 ревью).
        """
        if not user_ids:
            return {}
        results = await valkey.smismember(cls.REDIS_KEY, [str(uid) for uid in user_ids])
        return dict(zip(user_ids, (bool(r) for r in results), strict=True))

    @classmethod
    async def update_banlist(cls) -> None:
        """Обновляет глобальный бан-лист из внешнего источника."""
        url = settings.GBAN_LIST_URL
        if not url:
            logger.warning("GBAN_LIST_URL is not set. Skipping update.")
            return

        try:
            data = await cls._fetch_banlist(url)
            if data is None:
                return

            if not isinstance(data, list):
                logger.error("Unknown gban list format: %s", type(data))
                return

            ids: list[str] = [str(x) for x in data]

            if not ids:
                logger.info("Gban list is empty.")
                return

            await valkey.delete(cls.TEMP_KEY)

            chunk_size = 1000
            for i in range(0, len(ids), chunk_size):
                chunk = ids[i : i + chunk_size]
                await valkey.sadd(cls.TEMP_KEY, *chunk)

            await valkey.rename(cls.TEMP_KEY, cls.REDIS_KEY)

            logger.info("Updated gban list with %d users.", len(ids))

        except Exception as e:
            logger.exception("Error updating gban list: %s", e)

    @classmethod
    async def _fetch_banlist(cls, url: str) -> Any | None:
        """Скачать и разобрать список, повторяя запрос при сетевых сбоях."""
        for attempt in range(1, _FETCH_ATTEMPTS + 1):
            try:
                async with aiohttp.ClientSession() as session, session.get(url) as response:
                    if response.status != 200:
                        logger.error("Failed to fetch gban list: %d", response.status)
                        return None

                    try:
                        return await response.json()
                    except ValueError:
                        logger.error("Failed to parse gban list JSON")
                        return None

            except _TRANSIENT_ERRORS as e:
                if attempt < _FETCH_ATTEMPTS:
                    logger.warning(
                        "Failed to fetch gban list (attempt %d/%d): %s",
                        attempt,
                        _FETCH_ATTEMPTS,
                        e,
                    )
                    await asyncio.sleep(_FETCH_BACKOFF * attempt)
                else:
                    logger.warning("Failed to fetch gban list after %d attempts: %s", _FETCH_ATTEMPTS, e)
                    return None

        return None
