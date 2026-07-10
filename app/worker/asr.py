import logging
from dataclasses import dataclass

import aiohttp
from app.core.config import settings
from app.worker.http import get_session

logger = logging.getLogger(__name__)


@dataclass
class AsrResult:
    """Результат распознавания речи ASR-сервисом."""

    transcript: str
    language: str
    duration: float


async def transcribe(data: bytes, filename: str) -> AsrResult | None:
    """Распознать речь в аудио/видео через ASR-сервис.

    Возвращает AsrResult или None. НИКОГДА не бросает исключение: любая ошибка
    (сервис недоступен, 5xx/timeout, 413 skip, битый файл) → None + WARNING.
    Это сознательно: сбой ASR не должен ронять анализ триггера или крутить
    hot-loop (в отличие от inference — там post-hoc nack оправдан, тут нет).
    """
    if not settings.ASR_ENABLED:
        return None

    url = f"{settings.ASR_URL}/transcribe"
    token = settings.ASR_TOKEN.get_secret_value()
    form = aiohttp.FormData()
    form.add_field("file", data, filename=filename, content_type="application/octet-stream")

    try:
        session = await get_session()
        async with session.post(
            url,
            data=form,
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=settings.ASR_TIMEOUT),
        ) as response:
            if response.status != 200:
                body = await response.text()
                logger.warning("ASR %d for %s: %s", response.status, filename, body[:200])
                return None
            payload = await response.json()
            return AsrResult(
                transcript=str(payload.get("transcript", "")),
                language=str(payload.get("language", "")),
                duration=float(payload.get("duration", 0.0)),
            )
    except Exception as e:
        logger.warning("ASR request failed for %s: %s", filename, e)
        return None
