import logging
from typing import Annotated

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.utils.web_app import check_webapp_signature, safe_parse_webapp_init_data
from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.api.v1.endpoints.auth import verify_auth_token
from app.bot.instance import bot
from app.core.config import settings
from app.core.database import get_db
from app.db.models.user import User
from app.services.user_service import get_or_create_user


async def validate_init_data(
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """
    Проверяет initData от Telegram WebApp или Bearer токен (Telegram OIDC).
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
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid initData",
            ) from e

    elif auth_type == "Bearer":
        user_id = verify_auth_token(auth_data)
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        return {"type": "token", "user_id": user_id}

    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown authorization type",
        )


async def validate_init_data_from_query(
    auth: Annotated[str | None, Query()] = None,
    auth_type: Annotated[str | None, Query()] = None,
) -> dict:
    """
    Проверяет initData из query params (для SSE endpoints).
    """
    if not auth or not auth_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auth query parameters are missing",
        )

    if auth_type == "twa":
        try:
            if not check_webapp_signature(settings.BOT_TOKEN, auth):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid initData signature",
                )
            return {"type": "webapp", "data": auth}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid initData",
            ) from e

    elif auth_type == "token":
        user_id = verify_auth_token(auth)
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        return {"type": "token", "user_id": user_id}

    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown authorization type",
        )


async def get_current_admin_from_query(
    auth_info: Annotated[dict, Depends(validate_init_data_from_query)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Возвращает текущего администратора (для SSE endpoints).
    """
    return await _get_admin_from_auth_info(auth_info, session)


async def _get_user_from_auth_info(auth_info: dict, session: AsyncSession) -> User:
    """Общая логика извлечения пользователя из auth_info (без проверки прав)."""
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

    elif auth_info["type"] == "token":
        # Токен содержит только user_id — не обновляем профиль, только читаем
        user = await session.get(User, auth_info["user_id"])
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        return user

    return await get_or_create_user(
        session,
        user_id=user_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        language_code=language_code,
        is_premium=is_premium,
    )


async def _get_admin_from_auth_info(auth_info: dict, session: AsyncSession) -> User:
    """Общая логика получения админа из auth_info."""
    user = await _get_user_from_auth_info(auth_info, session)

    if not (user.is_bot_moderator or user.id in settings.BOT_ADMINS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not an admin or moderator",
        )

    return user


async def get_current_admin(
    auth_info: Annotated[dict, Depends(validate_init_data)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Возвращает текущего администратора или модератора.
    """
    return await _get_admin_from_auth_info(auth_info, session)


async def get_authenticated_user(
    auth_info: Annotated[dict, Depends(validate_init_data)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Получить аутентифицированного пользователя (без проверки прав бот-админа)."""
    return await _get_user_from_auth_info(auth_info, session)


async def require_chat_admin(user: User, chat_id: int) -> bool:
    """Проверить, что пользователь — админ чата или BOT_ADMIN.

    Возвращает is_creator: True для BOT_ADMIN/модератора (эквивалентные права) или
    реального создателя чата, False для обычного администратора. Вызывающий код
    переиспользует значение вместо повторного bot.get_chat_member на тот же chat_id
    (см. defect #5 ревью -- было два похода в Telegram на один GET/PATCH).
    """
    if user.is_bot_moderator or user.id in settings.BOT_ADMINS:
        return True
    try:
        member = await bot.get_chat_member(chat_id, user.id)
        if member.status in ("administrator", "creator"):
            return member.status == "creator"
    except (TelegramBadRequest, TelegramForbiddenError):
        raise HTTPException(status_code=403, detail="You are not an admin of this chat") from None
    except TelegramRetryAfter as e:
        raise HTTPException(
            status_code=503,
            detail="Telegram API rate limit exceeded, please retry",
            headers={"Retry-After": str(e.retry_after)},
        ) from None
    except Exception:
        logger.exception("Failed to verify chat membership for user %d in chat %d", user.id, chat_id)
        raise HTTPException(status_code=502, detail="Failed to verify chat membership") from None
    raise HTTPException(status_code=403, detail="You are not an admin of this chat")
