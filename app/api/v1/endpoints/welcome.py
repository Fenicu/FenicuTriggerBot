import logging
from typing import Annotated

from aiogram.types import BufferedInputFile
from aiogram.types import User as AiogramUser
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_authenticated_user, require_chat_admin
from app.bot.instance import bot
from app.core.config import settings
from app.core.database import get_db
from app.db.models.user import User
from app.services.chat_service import get_chat_with_ban_status
from app.services.welcome_service import send_welcome_message

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_CONTENT_TYPES = {
    "image/jpeg": "photo",
    "image/png": "photo",
    "video/mp4": "video",
    "image/gif": "animation",
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

MAGIC_BYTES = {
    b'\xff\xd8\xff': "image/jpeg",
    b'\x89PNG': "image/png",
    b'GIF8': "image/gif",
}


def validate_file_type(content: bytes, claimed_type: str) -> str | None:
    """Validate file type by magic bytes. Returns actual type or None."""
    # Video files (MP4) start with various signatures
    if claimed_type == "video/mp4":
        # ftyp box appears within first 12 bytes
        if b'ftyp' in content[:12]:
            return "video/mp4"
        return None
    # Check magic bytes for images
    for magic, mime in MAGIC_BYTES.items():
        if content[:len(magic)] == magic:
            return mime
    return None


@router.post("/{chat_id}/welcome-media")
async def upload_welcome_media(
    chat_id: int,
    file: UploadFile,
    user: Annotated[User, Depends(get_authenticated_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Загрузить медиа для приветствия. Отправляет в Telegram, возвращает file_id."""
    await require_chat_admin(user, chat_id)

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    actual_type = validate_file_type(content, file.content_type)
    if not actual_type or actual_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="File content doesn't match declared type")
    file_type = ALLOWED_CONTENT_TYPES[actual_type]
    input_file = BufferedInputFile(content, filename=file.filename or "upload")

    try:
        if file_type == "photo":
            msg = await bot.send_photo(settings.MODERATION_CHANNEL_ID, input_file)
            file_id = msg.photo[-1].file_id
        elif file_type == "video":
            msg = await bot.send_video(settings.MODERATION_CHANNEL_ID, input_file)
            file_id = msg.video.file_id
        else:  # animation
            msg = await bot.send_animation(settings.MODERATION_CHANNEL_ID, input_file)
            file_id = msg.animation.file_id

        # Удалить сообщение из канала
        try:
            await bot.delete_message(settings.MODERATION_CHANNEL_ID, msg.message_id)
        except Exception as e:
            logger.warning(f"Failed to delete temporary media message {msg.message_id}: {e}")

        return {"file_id": file_id, "file_type": file_type}

    except Exception as e:
        logger.exception(f"Failed to upload media: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload media") from e


@router.post("/{chat_id}/welcome-test")
async def test_welcome(
    chat_id: int,
    user: Annotated[User, Depends(get_authenticated_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Отправить тестовое приветствие пользователю."""
    await require_chat_admin(user, chat_id)

    chat, _ = await get_chat_with_ban_status(session, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if not chat.welcome_message:
        raise HTTPException(status_code=400, detail="Welcome message not set")

    try:
        tg_chat = await bot.get_chat(chat_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Cannot access chat info") from e

    mock_user = AiogramUser(
        id=user.id,
        is_bot=False,
        first_name=user.first_name or "User",
        last_name=user.last_name,
        username=user.username,
    )

    result = await send_welcome_message(bot, session, tg_chat, mock_user, chat)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to send test message")

    return {"status": "ok"}
