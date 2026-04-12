import logging

import aiofiles
from app.core.config import settings
from app.worker.http import get_session

logger = logging.getLogger(__name__)

# 50 MB in-memory limit for photos/stickers
MAX_MEMORY_SIZE = 50 * 1024 * 1024


async def get_telegram_file_url(file_id: str) -> str | None:
    """Получить URL файла из Telegram."""
    session = await get_session()
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/getFile?file_id={file_id}"
    if settings.TELEGRAM_BOT_API_URL:
        url = f"{settings.TELEGRAM_BOT_API_URL}/bot{settings.BOT_TOKEN}/getFile?file_id={file_id}"

    async with session.get(url) as response:
        if response.status != 200:
            return None
        data = await response.json()
        if not data.get("ok"):
            logger.error("Telegram API error: %s", data)
            return None

        file_path: str = data["result"]["file_path"]

        if settings.TELEGRAM_BOT_API_URL:
            # Fix for local Bot API returning absolute paths
            if file_path.startswith("/") and settings.BOT_TOKEN in file_path:
                file_path = file_path.split(settings.BOT_TOKEN, 1)[-1].lstrip("/")

            return f"{settings.TELEGRAM_BOT_API_URL}/file/bot{settings.BOT_TOKEN}/{file_path}"
        return f"https://api.telegram.org/file/bot{settings.BOT_TOKEN}/{file_path}"


async def download_file(url: str, max_size: int = MAX_MEMORY_SIZE) -> bytes | None:
    """Скачать файл в память с потоковым чтением и защитой от OOM.

    Stall detection handled by shared session (sock_read=30s).
    """
    session = await get_session()
    async with session.get(url) as response:
        if response.status != 200:
            logger.error("Failed to download file: %s", response.status)
            return None

        # Early exit if Content-Length exceeds limit
        if response.content_length and response.content_length > max_size:
            logger.warning(
                "File too large (%d bytes, limit %d), skipping",
                response.content_length,
                max_size,
            )
            return None

        # Stream chunks with size tracking
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.content.iter_chunked(65536):
            total += len(chunk)
            if total > max_size:
                logger.warning("Download exceeded size limit at %d bytes", total)
                return None
            chunks.append(chunk)

        return b"".join(chunks)


async def download_file_to_path(url: str, path: str) -> bool:
    """Скачать файл на диск потоково.

    Stall detection handled by shared session (sock_read=30s).
    No size limit — file goes straight to disk, ffmpeg only extracts one frame.
    """
    session = await get_session()
    async with session.get(url) as response:
        if response.status != 200:
            logger.error("Failed to download file: %s", response.status)
            return False
        async with aiofiles.open(path, "wb") as f:
            async for chunk in response.content.iter_chunked(65536):
                await f.write(chunk)
        return True
