import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.bot.instance import bot
from app.core.config import settings
from app.core.database import get_db
from app.core.storage import storage
from app.db.models.user import User
from app.schemas.admin import (
    PaginatedResponse,
    Pagination,
    UpdateUserRoleRequest,
    UserChatResponse,
    UserResponse,
)
from app.services.gban_service import GbanService
from app.services.user_service import get_user, get_user_chats, get_users
from app.worker.telegram import download_file, get_telegram_file_url

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=PaginatedResponse[UserResponse])
async def list_users(
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    query: str | None = None,
    sort_by: str = Query("created_at", pattern="^(created_at|updated_at|username|id|badges)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    is_premium: bool | None = None,
    is_trusted: bool | None = None,
    is_bot_moderator: bool | None = None,
) -> PaginatedResponse[UserResponse]:
    """Список пользователей."""
    users, total = await get_users(
        session,
        page,
        limit,
        query,
        sort_by,
        sort_order,
        is_premium,
        is_trusted,
        is_bot_moderator,
    )

    items = []
    for user in users:
        item = UserResponse.model_validate(user)
        item.is_gban = await GbanService.is_banned(user.id)
        items.append(item)

    total_pages = (total + limit - 1) // limit
    return PaginatedResponse(
        items=items,
        pagination=Pagination(
            page=page,
            limit=limit,
            total=total,
            total_pages=total_pages,
        ),
    )


@router.get("/{user_id}", response_model=UserResponse)
async def read_user(
    user_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
) -> UserResponse:
    """Получить пользователя."""
    user = await get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    response = UserResponse.model_validate(user)
    response.is_gban = await GbanService.is_banned(user.id)

    try:
        tg_chat = await bot.get_chat(user_id)
        old_photo_id = user.photo_id
        if tg_chat.photo:
            new_photo_id = tg_chat.photo.big_file_id
            if old_photo_id and old_photo_id != new_photo_id:
                await storage.delete_file(old_photo_id)

            user.photo_id = new_photo_id
            response.photo_id = new_photo_id
        else:
            if old_photo_id:
                await storage.delete_file(old_photo_id)

            user.photo_id = None
            response.photo_id = None
        await session.commit()
        await session.refresh(user)
    except Exception as e:
        logger.warning(f"Failed to update user info from Telegram for {user_id}: {e}")

    return response


@router.get("/{user_id}/photo")
async def get_user_photo(
    user_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
) -> Response:
    """Получить фото пользователя."""
    user = await get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.photo_id:
        try:
            tg_chat = await bot.get_chat(user_id)
            if tg_chat.photo:
                user.photo_id = tg_chat.photo.big_file_id
                await session.commit()
                await session.refresh(user)
            else:
                raise HTTPException(status_code=404, detail="Photo not found")
        except Exception as e:
            logger.warning(f"Failed to fetch user photo from Telegram: {e}")
            raise HTTPException(status_code=404, detail="Photo not found") from e

    cached_file = await storage.get_file(user.photo_id)
    if cached_file:
        media_type = cached_file.headers.get("Content-Type", "image/jpeg")
        return StreamingResponse(storage.stream_content(cached_file), media_type=media_type)

    file_url = await get_telegram_file_url(user.photo_id)
    if not file_url:
        raise HTTPException(status_code=404, detail="Photo URL not found")

    file_data = await download_file(file_url)
    if not file_data:
        raise HTTPException(status_code=404, detail="Failed to download photo")

    await storage.put_file(user.photo_id, file_data, content_type="image/jpeg")

    return Response(content=file_data, media_type="image/jpeg")


@router.post("/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: int,
    request: UpdateUserRoleRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
) -> UserResponse:
    """Обновить роли пользователя."""
    if request.is_bot_moderator is not None and admin.id not in settings.BOT_ADMINS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admins can manage moderators",
        )

    user = await get_user(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if request.is_trusted is not None:
        user.is_trusted = request.is_trusted
    if request.is_bot_moderator is not None:
        user.is_bot_moderator = request.is_bot_moderator

    await session.commit()
    await session.refresh(user)
    return user


@router.get("/{user_id}/chats", response_model=PaginatedResponse[UserChatResponse])
async def list_user_chats(
    user_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[UserChatResponse]:
    """Получить список чатов пользователя."""
    user_chats, total = await get_user_chats(session, user_id, page, limit)
    total_pages = (total + limit - 1) // limit

    return PaginatedResponse(
        items=[UserChatResponse.model_validate(uc) for uc in user_chats],
        pagination=Pagination(
            page=page,
            limit=limit,
            total=total,
            total_pages=total_pages,
        ),
    )
