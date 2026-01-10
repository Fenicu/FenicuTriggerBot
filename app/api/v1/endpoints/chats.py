import contextlib
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.bot.instance import bot
from app.core.database import get_db
from app.db.models.user import User
from app.schemas.admin import (
    BanChatRequest,
    ChatResponse,
    PaginatedResponse,
    Pagination,
    SendMessageRequest,
)
from app.services.chat_service import (
    ban_chat,
    get_chat_with_ban_status,
    get_chats,
    update_chat_settings,
)

router = APIRouter()


@router.get("", response_model=PaginatedResponse[ChatResponse])
async def list_chats(
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    query: str | None = None,
    include_private: bool = Query(False),
) -> PaginatedResponse[ChatResponse]:
    """Список чатов."""
    results, total = await get_chats(session, page, limit, query, include_private)
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
    chat, banned_chat = await get_chat_with_ban_status(session, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    item = ChatResponse.model_validate(chat)
    if banned_chat:
        item.is_banned = True
        item.ban_reason = banned_chat.reason
    return item


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
