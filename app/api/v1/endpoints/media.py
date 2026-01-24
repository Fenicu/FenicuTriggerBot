import gzip
import logging
import mimetypes
from collections.abc import AsyncGenerator
from typing import Any

import aiohttp
from aiogram.types import File
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import StreamingResponse

from app.bot.instance import bot

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/info")
async def get_media_info(file_id: str) -> dict[str, Any]:
    """
    Get information about a file from Telegram.
    """
    try:
        file: File = await bot.get_file(file_id)
        return {"file_size": file.file_size, "file_path": file.file_path}
    except Exception as e:
        logger.error(f"Error getting file info: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e


async def stream_file_content(url: str) -> AsyncGenerator[bytes]:
    async with aiohttp.ClientSession() as session, session.get(url) as response:
        if response.status != 200:
            logger.error(f"Failed to download file from {url}: {response.status}")
            return
        async for chunk in response.content.iter_chunked(8192):
            yield chunk


@router.get("/proxy")
async def proxy_media(file_id: str) -> Response:
    """
    Proxy a file from Telegram.
    If it's a TGS (sticker), decompress it and return JSON.
    Otherwise, stream the file.
    """
    try:
        file: File = await bot.get_file(file_id)
    except Exception as e:
        logger.error(f"Error getting file info: {e}")
        raise HTTPException(status_code=400, detail=str(e)) from e

    file_url = bot.session.api.file_url(bot.token, file.file_path)

    if file.file_path.endswith(".tgs"):
        try:
            async with aiohttp.ClientSession() as session, session.get(file_url) as response:
                if response.status != 200:
                    raise HTTPException(status_code=response.status, detail="Failed to download file")
                content = await response.read()

                decompressed_content = gzip.decompress(content)

                return Response(content=decompressed_content, media_type="application/json")
        except Exception as e:
            logger.error(f"Error processing TGS file: {e}")
            raise HTTPException(status_code=500, detail=f"Error processing TGS file: {e}") from e

    mime_type, _ = mimetypes.guess_type(file.file_path)
    if not mime_type:
        mime_type = "application/octet-stream"

    return StreamingResponse(stream_file_content(file_url), media_type=mime_type)
