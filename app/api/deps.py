import hashlib
import hmac
import time
from typing import Annotated
from urllib.parse import parse_qsl

from aiogram.utils.web_app import check_webapp_signature, safe_parse_webapp_init_data
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.db.models.user import User
from app.services.user_service import get_or_create_user


def check_login_widget_signature(token: str, data: dict) -> bool:
    """Проверяет подпись данных от Telegram Login Widget."""
    try:
        hash_ = data.get("hash")
        if not hash_:
            return False

        auth_date = int(data.get("auth_date", 0))
        if time.time() - auth_date > 86400:
            return False

        data_check_arr = []
        for key, value in sorted(data.items()):
            if key != "hash":
                data_check_arr.append(f"{key}={value}")
        data_check_string = "\n".join(data_check_arr)

        secret_key = hashlib.sha256(token.encode()).digest()
        hmac_string = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        return hmac_string == hash_
    except Exception:
        return False


async def validate_init_data(
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """
    Проверяет initData от Telegram WebApp или Login Widget.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is missing",
        )

    parts = authorization.split(" ", 1)
    if len(parts) != 2:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format",
        )

    auth_type, auth_data = parts

    if auth_type == "twa-init-data":
        try:
            if not check_webapp_signature(settings.BOT_TOKEN, auth_data):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid initData signature",
                )
            return {"type": "webapp", "data": auth_data}
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid initData",
            ) from e

    elif auth_type == "login-widget-data":
        try:
            data = dict(parse_qsl(auth_data))
            if not check_login_widget_signature(settings.BOT_TOKEN, data):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid login widget signature",
                )
            return {"type": "widget", "data": data}
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid login widget data",
            ) from e

    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown authorization type",
        )


async def get_current_admin(
    auth_info: Annotated[dict, Depends(validate_init_data)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Возвращает текущего администратора или модератора.
    """
    user_id = None
    username = None
    first_name = None
    last_name = None
    language_code = None
    is_premium = None

    if auth_info["type"] == "webapp":
        try:
            web_app_data = safe_parse_webapp_init_data(settings.BOT_TOKEN, auth_info["data"])
            user_data = web_app_data.user
            if not user_data:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="User data missing in initData",
                )
            user_id = user_data.id
            username = user_data.username
            first_name = user_data.first_name
            last_name = user_data.last_name
            language_code = user_data.language_code
            is_premium = user_data.is_premium
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid initData",
            ) from e

    elif auth_info["type"] == "widget":
        data = auth_info["data"]
        try:
            user_id = int(data["id"])
            username = data.get("username")
            first_name = data.get("first_name")
            last_name = data.get("last_name")
            language_code = data.get("language_code")
            is_premium = None
        except (ValueError, KeyError) as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid user data in login widget",
            ) from e

    user = await get_or_create_user(
        session,
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        language_code=language_code,
        is_premium=is_premium,
    )

    if not (user.is_bot_moderator or user.id in settings.BOT_ADMINS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not an admin or moderator",
        )

    return user
