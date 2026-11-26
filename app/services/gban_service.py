import asyncio
import codecs
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

# Читаем тело ответа кусками, чтобы не держать весь список в памяти
_CHUNK_SIZE = 64 * 1024
# Пишем в Valkey пачками, не накапливая список целиком
_BATCH_SIZE = 200_000

_WHITESPACE = frozenset(" \t\r\n")
_MAX_TOKEN_LEN = 20


class _BanlistFormatError(Exception):
    """Ответ источника не похож на JSON-массив числовых id."""


class _BanlistParser:
    """Инкрементальный сканер JSON-массива id.

    Принимает int и строки из цифр, числа могут разрываться между кусками тела.
    """

    _BEFORE = 0
    _IN_LIST = 1
    _IN_NUMBER = 2
    _IN_STRING = 3
    _AFTER = 4

    def __init__(self) -> None:
        self._state = self._BEFORE
        self._token: list[str] = []
        self._count = 0
        self._needs_value = False
        self._after_value = False

    @property
    def count(self) -> int:
        return self._count

    def feed(self, text: str) -> list[int]:
        ids: list[int] = []
        for ch in text:
            while True:
                if self._state == self._BEFORE:
                    if ch in _WHITESPACE:
                        break
                    if ch == "[":
                        self._state = self._IN_LIST
                        break
                    raise _BanlistFormatError(f"expected '[', got {ch!r}")

                if self._state == self._IN_LIST:
                    if ch in _WHITESPACE:
                        break
                    if ch == ",":
                        if not self._after_value:
                            raise _BanlistFormatError("unexpected ','")
                        self._after_value = False
                        self._needs_value = True
                        break
                    if ch == "]":
                        if self._needs_value:
                            raise _BanlistFormatError("trailing ','")
                        self._state = self._AFTER
                        break
                    if ch == '"':
                        self._state = self._IN_STRING
                        self._token = []
                        break
                    if ch == "-" or "0" <= ch <= "9":
                        self._state = self._IN_NUMBER
                        self._token = [ch]
                        break
                    raise _BanlistFormatError(f"unexpected character {ch!r}")

                if self._state == self._IN_NUMBER:
                    if "0" <= ch <= "9":
                        self._token.append(ch)
                        if len(self._token) > _MAX_TOKEN_LEN:
                            raise _BanlistFormatError("number is too long")
                        break
                    self._finish_number(ids)
                    self._state = self._IN_LIST
                    continue

                if self._state == self._IN_STRING:
                    if "0" <= ch <= "9":
                        self._token.append(ch)
                        if len(self._token) > _MAX_TOKEN_LEN:
                            raise _BanlistFormatError("number is too long")
                        break
                    if ch == '"':
                        if not self._token:
                            raise _BanlistFormatError("empty string id")
                        self._finish_number(ids)
                        self._state = self._IN_LIST
                        break
                    raise _BanlistFormatError(f"unexpected character {ch!r} in string id")

                if ch in _WHITESPACE:
                    break
                raise _BanlistFormatError(f"unexpected data after list: {ch!r}")

        return ids

    def finish(self) -> None:
        if self._state != self._AFTER:
            raise _BanlistFormatError("list is not closed or truncated")

    def _finish_number(self, ids: list[int]) -> None:
        raw = "".join(self._token)
        self._token = []
        if raw in ("", "-"):
            raise _BanlistFormatError("empty number")
        try:
            value = int(raw)
        except ValueError as exc:
            raise _BanlistFormatError(f"invalid number {raw!r}") from exc
        self._count += 1
        ids.append(value)
        self._after_value = True
        self._needs_value = False


class GbanService:
    REDIS_KEY = "gban:users"
    TEMP_KEY = "gban:users:temp"
    META_KEY = "gban:meta"

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
            meta = await cls._load_meta()
            for attempt in range(1, _FETCH_ATTEMPTS + 1):
                try:
                    await cls._fetch_and_store(url, meta)
                    return
                except _BanlistFormatError as e:
                    logger.error("Failed to parse gban list: %s", e)
                    await cls._clear_temp()
                    return
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
                        await cls._clear_temp()
                        return
        except Exception as e:
            logger.exception("Error updating gban list: %s", e)

    @classmethod
    async def _load_meta(cls) -> dict[str, Any]:
        return await valkey.hgetall(cls.META_KEY) or {}

    @classmethod
    async def _clear_temp(cls) -> None:
        await valkey.delete(cls.TEMP_KEY)

    @classmethod
    async def _fetch_and_store(cls, url: str, meta: dict[str, Any]) -> None:
        headers: dict[str, str] = {}
        etag = meta.get("etag")
        last_modified = meta.get("last_modified")
        if etag:
            headers["If-None-Match"] = str(etag)
        if last_modified:
            headers["If-Modified-Since"] = str(last_modified)

        async with (
            aiohttp.ClientSession() as session,
            session.get(url, headers=headers) as response,
        ):
            if response.status == 304:
                logger.debug("Gban list is not modified (304).")
                return
            if response.status != 200:
                logger.error("Failed to fetch gban list: %d", response.status)
                return
            await cls._stream_and_store(response, meta)

    @classmethod
    async def _stream_and_store(cls, response: aiohttp.ClientResponse, meta: dict[str, Any]) -> None:
        await cls._clear_temp()

        decoder = codecs.getincrementaldecoder("utf-8")()
        parser = _BanlistParser()
        batch: list[int] = []

        try:
            async for chunk in response.content.iter_chunked(_CHUNK_SIZE):
                text = decoder.decode(chunk)
                batch.extend(parser.feed(text))
                while len(batch) >= _BATCH_SIZE:
                    await valkey.sadd(cls.TEMP_KEY, *batch[:_BATCH_SIZE])
                    del batch[:_BATCH_SIZE]

            batch.extend(parser.feed(decoder.decode(b"", final=True)))
            parser.finish()
        except UnicodeDecodeError as exc:
            raise _BanlistFormatError("response is not valid UTF-8") from exc

        if batch:
            await valkey.sadd(cls.TEMP_KEY, *batch)

        count = parser.count
        previous = cls._previous_count(meta)
        if previous and count < previous * 0.5:
            logger.warning(
                "Gban list looks truncated: %d ids vs %d previous, keeping the old list",
                count,
                previous,
            )
            await cls._clear_temp()
            return

        if count == 0:
            logger.info("Gban list is empty.")
            await cls._clear_temp()
            return

        await valkey.rename(cls.TEMP_KEY, cls.REDIS_KEY)

        mapping: dict[str, Any] = {"count": count}
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")
        if etag:
            mapping["etag"] = etag
        if last_modified:
            mapping["last_modified"] = last_modified
        await valkey.hset(cls.META_KEY, mapping=mapping)
        if not etag:
            await valkey.hdel(cls.META_KEY, "etag")
        if not last_modified:
            await valkey.hdel(cls.META_KEY, "last_modified")

        logger.info("Updated gban list with %d users.", count)

    @staticmethod
    def _previous_count(meta: dict[str, Any]) -> int:
        try:
            return int(meta.get("count", 0) or 0)
        except (TypeError, ValueError):
            return 0
