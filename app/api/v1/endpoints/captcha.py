import logging
from datetime import datetime
from typing import Any

from aiogram.utils.web_app import safe_parse_webapp_init_data
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, validate_init_data
from app.bot.instance import bot
from app.core.config import settings
from app.core.i18n import translator_hub
from app.core.valkey import valkey
from app.db.models.captcha_session import ChatCaptchaSession
from app.db.models.user import User

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
        chat = await bot.get_chat(captcha_session.chat_id)
        if chat.permissions:
            await bot.restrict_chat_member(
                chat_id=captcha_session.chat_id,
                user_id=user_id,
                permissions=chat.permissions,
            )

        await bot.unban_chat_member(
            chat_id=captcha_session.chat_id,
            user_id=user_id,
            only_if_banned=False,
        )

        lang_code = await valkey.get(f"lang:{captcha_session.chat_id}")
        i18n = translator_hub.get_translator_by_locale(lang_code or "ru")

        await bot.edit_message_text(
            chat_id=captcha_session.chat_id,
            message_id=captcha_session.message_id,
            text=i18n.get("captcha-success"),
        )
    except Exception as e:
        logger.error(f"Failed to unmute user or edit message: {e}")

    return {"ok": True}
