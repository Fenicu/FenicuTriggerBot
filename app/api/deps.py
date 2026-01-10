from typing import Annotated

from aiogram.utils.web_app import check_webapp_signature, safe_parse_webapp_init_data
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.db.models.user import User
from app.services.user_service import get_or_create_user


async def validate_init_data(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """
    Проверяет initData от Telegram WebApp.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is missing",
        )

    parts = authorization.split(" ")
    if len(parts) != 2 or parts[0] != "twa-init-data":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
        )

    init_data = parts[1]

    try:
        if not check_webapp_signature(settings.BOT_TOKEN, init_data):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid initData signature",
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid initData",
        ) from e

    return init_data


async def get_current_admin(
    init_data: Annotated[str, Depends(validate_init_data)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Возвращает текущего администратора или модератора.
    """
    try:
        web_app_data = safe_parse_webapp_init_data(settings.BOT_TOKEN, init_data)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid initData",
        ) from e

    user_data = web_app_data.user
    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User data missing in initData",
        )

    user = await get_or_create_user(
        session,
        user_id=user_data.id,
        username=user_data.username,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        language_code=user_data.language_code,
        is_premium=user_data.is_premium,
    )

    if not (user.is_bot_moderator or user.id in settings.BOT_ADMINS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not an admin or moderator",
        )

    return user
