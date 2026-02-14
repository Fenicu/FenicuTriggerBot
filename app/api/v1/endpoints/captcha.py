import logging
from datetime import datetime, timedelta
from typing import Any

from aiogram.types import ChatPermissions
from aiogram.utils.web_app import safe_parse_webapp_init_data
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, validate_init_data
from app.bot.instance import bot
from app.core.config import settings
from app.core.i18n import ROOT_LOCALE, translator_hub
from app.core.valkey import valkey
from app.db.models.captcha_session import ChatCaptchaSession
from app.db.models.chat import Chat
from app.db.models.user import User
from app.services.user_service import get_or_create_user

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/check")
async def check_captcha_status(
    auth_info: dict = Depends(validate_init_data),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Проверяет статус капчи для пользователя.
    """
    try:
        if auth_info["type"] != "webapp":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only WebApp authentication is supported",
            )

        web_app_data = safe_parse_webapp_init_data(settings.BOT_TOKEN, auth_info["data"])
        if not web_app_data.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User data missing",
            )
        user_id = web_app_data.user.id
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid initData",
        ) from e

    query = select(ChatCaptchaSession).where(
        ChatCaptchaSession.user_id == user_id,
        ChatCaptchaSession.is_completed == False,  # noqa: E712
        ChatCaptchaSession.expires_at > datetime.now().astimezone(),
    )
    result = await session.execute(query)
    captcha_session = result.scalars().first()

    if captcha_session:
        return {
            "ok": True,
            "status": "pending",
            "session_id": captcha_session.id,
            "chat_id": captcha_session.chat_id,
        }

    return {"ok": True, "status": "no_session"}


@router.post("/solve")
async def solve_captcha(
    auth_info: dict = Depends(validate_init_data),
    session: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """
    Подтверждает прохождение капчи.
    """
    try:
        if auth_info["type"] != "webapp":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only WebApp authentication is supported",
            )

        web_app_data = safe_parse_webapp_init_data(settings.BOT_TOKEN, auth_info["data"])
        if not web_app_data.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User data missing",
            )
        user_id = web_app_data.user.id
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid initData",
        ) from e

    query = select(ChatCaptchaSession).where(
        ChatCaptchaSession.user_id == user_id,
        ChatCaptchaSession.is_completed == False,  # noqa: E712
        ChatCaptchaSession.expires_at > datetime.now().astimezone(),
    )
    result = await session.execute(query)
    captcha_session = result.scalars().first()

    if not captcha_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active captcha session not found",
        )

    captcha_session.is_completed = True

    user = await session.get(User, user_id)
    if user:
        user.has_passed_captcha = True

    await session.commit()

    try:
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_change_info=True,
            can_invite_users=True,
            can_pin_messages=True,
            can_manage_topics=True,
        )
        await bot.restrict_chat_member(
            chat_id=captcha_session.chat_id,
            user_id=user_id,
            permissions=permissions,
        )

        lang_code = await valkey.get(f"lang:{captcha_session.chat_id}")
        i18n = translator_hub.get_translator_by_locale(lang_code or ROOT_LOCALE)

        chat = await session.get(Chat, captcha_session.chat_id)
        if chat and chat.welcome_enabled:
            await bot.edit_message_reply_markup(
                chat_id=captcha_session.chat_id,
                message_id=captcha_session.message_id,
                reply_markup=None,
            )
        else:
            await bot.edit_message_text(
                chat_id=captcha_session.chat_id,
                message_id=captcha_session.message_id,
                text=i18n.captcha.success(),
            )
    except Exception as e:
        logger.error(f"Failed to unmute user or edit message: {e}")

    return {"ok": True}


@router.post("/debug")
async def create_debug_captcha(
    auth_info: dict = Depends(validate_init_data),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Создает тестовую сессию капчи для отладки (только для админов).
    """
    try:
        if auth_info["type"] != "webapp":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only WebApp authentication is supported",
            )

        web_app_data = safe_parse_webapp_init_data(settings.BOT_TOKEN, auth_info["data"])
        if not web_app_data.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User data missing",
            )
        user_id = web_app_data.user.id
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid initData",
        ) from e

    user = await session.get(User, user_id)
    if not user:
        user = await get_or_create_user(
            session=session,
            user_id=user_id,
            username=web_app_data.user.username,
            first_name=web_app_data.user.first_name,
            last_name=web_app_data.user.last_name,
            language_code=web_app_data.user.language_code,
            is_premium=web_app_data.user.is_premium,
        )

    if user_id not in settings.BOT_ADMINS and not user.is_bot_moderator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: admin only",
        )

    expires_at = datetime.now().astimezone() + timedelta(minutes=10)  # Дольше для отладки

    captcha_session = ChatCaptchaSession(
        chat_id=user_id,
        user_id=user_id,
        expires_at=expires_at,
        message_id=0,
    )
    session.add(captcha_session)
    await session.commit()
    await session.refresh(captcha_session)

    return {
        "ok": True,
        "session_id": captcha_session.id,
        "expires_at": expires_at.isoformat(),
    }
