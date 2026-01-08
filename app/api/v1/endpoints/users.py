from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.config import settings
from app.core.database import get_db
from app.db.models.user import User
from app.schemas.admin import (
    PaginatedResponse,
    Pagination,
    UpdateUserRoleRequest,
    UserResponse,
)
from app.services.user_service import get_user, get_users

router = APIRouter()


@router.get("", response_model=PaginatedResponse[UserResponse])
async def list_users(
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    query: str | None = None,
) -> PaginatedResponse[UserResponse]:
    """Список пользователей."""
    users, total = await get_users(session, page, limit, query)
    total_pages = (total + limit - 1) // limit
    return PaginatedResponse(
        items=users,
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
    return user


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
