import base64
import gzip
import hashlib
import hmac
import json
import logging
import mimetypes
import time
from collections.abc import AsyncGenerator
from typing import Annotated, Any

import aiohttp
from aiogram.types import File
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, validate_init_data
from app.bot.instance import bot
from app.core.config import settings
from app.core.database import get_db
from app.core.storage import storage
from app.db.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)

# Ссылка на медиа используется напрямую в <img>/<video> src на фронте, где
# заголовок Authorization не отправить — поэтому короткоживущий подписанный
# токен на file_id, помимо обычного admin-Depends. 1 час достаточно для рендера
# страницы модерации и не оставляет file_id «вечно скачиваемым» по старой ссылке.
MEDIA_TOKEN_TTL_SECONDS = 60 * 60


def generate_media_token(file_id: str, ttl_seconds: int = MEDIA_TOKEN_TTL_SECONDS) -> str:
    """Генерирует короткоживущий подписанный токен доступа к медиафайлу по file_id."""
    payload = json.dumps(
        {"fid": file_id, "exp": int(time.time()) + ttl_seconds},
        separators=(",", ":"),
    )
    encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    signature = hmac.new(settings.BOT_TOKEN.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def verify_media_token(file_id: str, token: str) -> bool:
    """Проверяет токен медиа: подпись, привязку к file_id и срок годности."""
    parts = token.split(".")
    if len(parts) != 2:
        return False

    encoded, signature = parts
    expected_signature = hmac.new(settings.BOT_TOKEN.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return False

    padded = encoded + "=" * (-len(encoded) % 4)
    try:
        payload = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, UnicodeDecodeError):
        return False

    if payload.get("fid") != file_id:
        return False

    return payload.get("exp", 0) >= time.time()


async def verify_media_access(
    file_id: str,
    session: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[str | None, Query()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """
    Доступ к медиа разрешён ЛИБО валидному админу/модератору (initData/Bearer),
    ЛИБО по подписанному короткоживущему токену, привязанному к этому file_id.
    """
    if token and verify_media_token(file_id, token):
        return

    auth_info = await validate_init_data(authorization)
    await get_current_admin(auth_info=auth_info, session=session)


@router.get("/token")
async def get_media_token(
    file_id: str,
    admin: Annotated[User, Depends(get_current_admin)],
) -> dict[str, Any]:
    """
    Выдаёт короткоживущий подписанный токен для доступа к /media/info и /media/proxy
    без заголовка Authorization — для встраивания в атрибуты src на фронте.
    """
    return {"token": generate_media_token(file_id), "expires_in": MEDIA_TOKEN_TTL_SECONDS}


@router.get("/info")
async def get_media_info(
    file_id: str,
    _access: Annotated[None, Depends(verify_media_access)],
) -> dict[str, Any]:
    """
    Get information about a file from Telegram.
    """
    try:
        file: File = await bot.get_file(file_id)
        return {"file_size": file.file_size, "file_path": file.file_path}
    except Exception as e:
        logger.exception("Error getting file info for file_id=%s", file_id)
        raise HTTPException(status_code=400, detail="Не удалось получить информацию о файле") from e


async def stream_file_content(url: str) -> AsyncGenerator[bytes]:
    async with aiohttp.ClientSession() as session, session.get(url) as response:
        if response.status != 200:
            logger.error(f"Failed to download file from {url}: {response.status}")
            return
        async for chunk in response.content.iter_chunked(8192):
            yield chunk


@router.get("/proxy")
async def proxy_media(
    file_id: str,
    _access: Annotated[None, Depends(verify_media_access)],
) -> Response:
    """
    Proxy a file from Telegram.
    If it's a TGS (sticker), decompress it and return JSON.
    Otherwise, stream the file.
    """
    cached = await storage.get_file(file_id)
    if cached:
        data, media_type = cached
        return Response(content=data, media_type=media_type)

    try:
        file: File = await bot.get_file(file_id)
    except Exception as e:
        logger.exception("Error getting file info for file_id=%s", file_id)
        raise HTTPException(status_code=400, detail="Не удалось получить информацию о файле") from e

    file_url = bot.session.api.file_url(bot.token, file.file_path)

    if file.file_path.endswith(".tgs"):
        try:
            async with aiohttp.ClientSession() as session, session.get(file_url) as response:
                if response.status != 200:
                    raise HTTPException(status_code=response.status, detail="Failed to download file")
                content = await response.read()

                decompressed_content = gzip.decompress(content)

                await storage.put_file(file_id, decompressed_content, content_type="application/json")

                return Response(content=decompressed_content, media_type="application/json")
        except Exception as e:
            logger.exception("Error processing TGS file for file_id=%s", file_id)
            raise HTTPException(status_code=500, detail="Не удалось обработать файл стикера") from e

    mime_type, _ = mimetypes.guess_type(file.file_path)
    if not mime_type:
        mime_type = "application/octet-stream"

    try:
        async with aiohttp.ClientSession() as session, session.get(file_url) as response:
            if response.status != 200:
                raise HTTPException(status_code=response.status, detail="Failed to download file")
            content = await response.read()

            await storage.put_file(file_id, content, content_type=mime_type)

            return Response(content=content, media_type=mime_type)
    except Exception as e:
        logger.exception("Error processing file for file_id=%s", file_id)
        raise HTTPException(status_code=500, detail="Не удалось загрузить файл") from e
