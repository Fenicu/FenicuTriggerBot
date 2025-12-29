import logging

import aiohttp
from app.core.config import settings

logger = logging.getLogger(__name__)


async def get_telegram_file_url(file_id: str) -> str | None:
    """Получить URL файла из Telegram."""
    async with aiohttp.ClientSession() as session:
        url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/getFile?file_id={file_id}"
        if settings.TELEGRAM_BOT_API_URL:
            url = f"{settings.TELEGRAM_BOT_API_URL}/bot{settings.BOT_TOKEN}/getFile?file_id={file_id}"

        async with session.get(url) as response:
            if response.status != 200:
                logger.error(f"Failed to get file info: {response.status}")
                return None
            data = await response.json()
            if not data.get("ok"):
                logger.error(f"Telegram API error: {data}")
                return None

            file_path = data["result"]["file_path"]

            if settings.TELEGRAM_BOT_API_URL:
                return f"{settings.TELEGRAM_BOT_API_URL}/file/bot{settings.BOT_TOKEN}/{file_path}"
            return f"https://api.telegram.org/file/bot{settings.BOT_TOKEN}/{file_path}"


async def download_file(url: str) -> bytes | None:
    """Скачать файл."""
    async with aiohttp.ClientSession() as session, session.get(url) as response:
        if response.status != 200:
            logger.error(f"Failed to download file: {response.status}")
            return None
        return await response.read()
