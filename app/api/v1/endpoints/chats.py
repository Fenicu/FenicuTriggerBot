import contextlib
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.bot.instance import bot
from app.core.database import get_db
from app.db.models.user import User
from app.schemas.admin import (
    BanChatRequest,
    ChatResponse,
    ChatUserResponse,
    PaginatedResponse,
    Pagination,
    SendMessageRequest,
    TriggerResponse,
)
from app.services.chat_service import (
    ban_chat,
    get_chat_users,
    get_chat_with_ban_status,
    get_chats,
    get_or_create_chat,
    update_chat_settings,
)
from app.services.trigger_service import get_trigger_by_id, get_triggers_count, get_triggers_paginated
from app.worker.telegram import download_file, get_telegram_file_url

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=PaginatedResponse[ChatResponse])
async def list_chats(
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    query: str | None = None,
    include_private: bool = Query(False),
    sort_by: str = Query("created_at", pattern="^(created_at|updated_at|title|id)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    is_active: bool | None = None,
    is_trusted: bool | None = None,
    is_banned: bool | None = None,
    chat_type: str | None = None,
) -> PaginatedResponse[ChatResponse]:
    """Список чатов."""
    results, total = await get_chats(
        session,
        page,
        limit,
        query,
        include_private,
        sort_by,
        sort_order,
        is_active,
        is_trusted,
        is_banned,
        chat_type,
    )
    total_pages = (total + limit - 1) // limit

    items = []
    for chat, banned_chat in results:
        item = ChatResponse.model_validate(chat)
        if banned_chat:
            item.is_banned = True
            item.ban_reason = banned_chat.reason
        items.append(item)

    return PaginatedResponse(
        items=items,
        pagination=Pagination(
            page=page,
            limit=limit,
            total=total,
            total_pages=total_pages,
        ),
    )


@router.get("/{chat_id}", response_model=ChatResponse)
async def read_chat(
    chat_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
) -> ChatResponse:
    """Получить чат."""
    try:
        tg_chat = await bot.get_chat(chat_id)
        photo_id = None
        if tg_chat.photo:
            photo_id = tg_chat.photo.big_file_id

        await get_or_create_chat(
            session,
            chat_id=chat_id,
            title=tg_chat.title,
            username=tg_chat.username,
            type=tg_chat.type,
            description=tg_chat.description,
            invite_link=tg_chat.invite_link,
            photo_id=photo_id,
        )
    except Exception as e:
        logger.warning(f"Failed to update chat info from Telegram for {chat_id}: {e}")

    chat, banned_chat = await get_chat_with_ban_status(session, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    triggers_count = await get_triggers_count(session, chat_id)

    item = ChatResponse.model_validate(chat)
    item.triggers_count = triggers_count
    if banned_chat:
        item.is_banned = True
        item.ban_reason = banned_chat.reason
    return item


@router.get("/{chat_id}/photo")
async def get_chat_photo(
    chat_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
) -> Response:
    """Получить фото чата."""
    chat, _ = await get_chat_with_ban_status(session, chat_id)
    if not chat or not chat.photo_id:
        raise HTTPException(status_code=404, detail="Photo not found")

    file_url = await get_telegram_file_url(chat.photo_id)
    if not file_url:
        raise HTTPException(status_code=404, detail="Photo URL not found")

    file_data = await download_file(file_url)
    if not file_data:
        raise HTTPException(status_code=404, detail="Failed to download photo")

    return Response(content=file_data, media_type="image/jpeg")


@router.post("/{chat_id}/trust", response_model=ChatResponse)
async def toggle_chat_trust(
    chat_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
) -> ChatResponse:
    """Переключить доверие к чату."""
    chat, banned_chat = await get_chat_with_ban_status(session, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    chat = await update_chat_settings(session, chat_id, is_trusted=not chat.is_trusted)

    item = ChatResponse.model_validate(chat)
    if banned_chat:
        item.is_banned = True
        item.ban_reason = banned_chat.reason
    return item


@router.post("/{chat_id}/ban", response_model=ChatResponse)
async def ban_chat_endpoint(
    chat_id: int,
    request: BanChatRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
) -> ChatResponse:
    """Забанить чат."""
    chat, _ = await get_chat_with_ban_status(session, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    banned_chat = await ban_chat(session, chat_id, request.reason)

    with contextlib.suppress(Exception):
        await bot.leave_chat(chat_id)

    item = ChatResponse.model_validate(chat)
    item.is_banned = True
    item.ban_reason = banned_chat.reason
    return item


@router.post("/{chat_id}/leave")
async def leave_chat_endpoint(
    chat_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
) -> dict[str, str]:
    """Бот покидает чат."""
    try:
        await bot.leave_chat(chat_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to leave chat: {e}") from e
    return {"status": "ok"}


@router.post("/{chat_id}/message")
async def send_message_endpoint(
    chat_id: int,
    request: SendMessageRequest,
    admin: Annotated[User, Depends(get_current_admin)],
) -> dict[str, str]:
    """Отправить сообщение в чат."""
    try:
        await bot.send_message(chat_id, request.text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to send message: {e}") from e
    return {"status": "ok"}


@router.get("/{chat_id}/triggers", response_model=PaginatedResponse[TriggerResponse])
async def list_chat_triggers(
    chat_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[TriggerResponse]:
    """Получить триггеры чата."""
    triggers, total = await get_triggers_paginated(session, chat_id, page, limit)
    total_pages = (total + limit - 1) // limit

    return PaginatedResponse(
        items=[TriggerResponse.model_validate(t) for t in triggers],
        pagination=Pagination(
            page=page,
            limit=limit,
            total=total,
            total_pages=total_pages,
        ),
    )


@router.get("/{chat_id}/triggers/{trigger_id}/image")
async def get_trigger_image(
    chat_id: int,
    trigger_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
) -> Response:
    """Получить изображение триггера."""
    trigger = await get_trigger_by_id(session, trigger_id)
    if not trigger or trigger.chat_id != chat_id:
        raise HTTPException(status_code=404, detail="Trigger not found")

    content = trigger.content
    file_id = None
    media_type = "image/jpeg"

    if content.get("photo"):
        file_id = content["photo"][-1]["file_id"]
    elif content.get("sticker"):
        file_id = content["sticker"]["file_id"]
        media_type = "image/webp"

    if not file_id:
        raise HTTPException(status_code=404, detail="Image not found in trigger")

    file_url = await get_telegram_file_url(file_id)
    if not file_url:
        raise HTTPException(status_code=404, detail="Image URL not found")

    file_data = await download_file(file_url)
    if not file_data:
        raise HTTPException(status_code=404, detail="Failed to download image")

    return Response(content=file_data, media_type=media_type)


@router.get("/{chat_id}/users", response_model=PaginatedResponse[ChatUserResponse])
async def list_chat_users(
    chat_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[ChatUserResponse]:
    """Получить список пользователей чата."""
    chat_users, total = await get_chat_users(session, chat_id, page, limit)
    total_pages = (total + limit - 1) // limit

    return PaginatedResponse(
        items=[ChatUserResponse.model_validate(cu) for cu in chat_users],
        pagination=Pagination(
            page=page,
            limit=limit,
            total=total,
            total_pages=total_pages,
        ),
    )
