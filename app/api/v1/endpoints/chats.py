import contextlib
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_authenticated_user, get_current_admin, require_chat_admin
from app.bot.instance import bot
from app.core.config import settings
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
    UpdateChatSettingsRequest,
)
from app.schemas.chat_settings import AuditLogEntry, ChatFullSettingsResponse, UpdateChatFullSettingsRequest
from app.services.audit_service import check_section_access, get_audit_log, record_settings_changes
from app.services.chat_service import (
    ban_chat,
    get_chat_users,
    get_chat_with_ban_status,
    get_chats,
    get_or_create_chat,
    update_chat_settings,
    update_chat_settings_specific,
)
from app.services.trigger_service import (
    get_trigger_by_id,
    get_triggers_count,
    get_triggers_filtered,
)
from app.worker.telegram import download_file, get_telegram_file_url

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{chat_id}/full-settings", response_model=ChatFullSettingsResponse)
async def get_full_settings(
    chat_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_authenticated_user)],
) -> ChatFullSettingsResponse:
    """Получить полные настройки чата (для webapp)."""
    await require_chat_admin(user, chat_id)
    chat, _ = await get_chat_with_ban_status(session, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Check if user is chat creator
    is_creator = False
    if user.is_bot_moderator or user.id in settings.BOT_ADMINS:
        is_creator = True
    else:
        try:
            member = await bot.get_chat_member(chat_id, user.id)
            is_creator = member.status == "creator"
        except Exception:
            logger.debug(f"Could not determine creator status for user {user.id} in chat {chat_id}")

    response = ChatFullSettingsResponse.model_validate(chat)
    response.is_creator = is_creator
    return response


@router.patch("/{chat_id}/full-settings", response_model=ChatFullSettingsResponse)
async def update_full_settings(
    chat_id: int,
    request: UpdateChatFullSettingsRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_authenticated_user)],
) -> ChatFullSettingsResponse:
    """Обновить настройки чата (для webapp)."""
    await require_chat_admin(user, chat_id)
    chat, _ = await get_chat_with_ban_status(session, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Check if user is chat creator
    is_creator = False
    if user.is_bot_moderator or user.id in settings.BOT_ADMINS:
        is_creator = True
    else:
        try:
            member = await bot.get_chat_member(chat_id, user.id)
            is_creator = member.status == "creator"
        except Exception:
            logger.debug(f"Could not determine creator status for user {user.id} in chat {chat_id}")

    update_data = request.model_dump(exclude_unset=True)

    # is_trusted — только для BOT_ADMIN/модераторов
    if "is_trusted" in update_data and not (user.is_bot_moderator or user.id in settings.BOT_ADMINS):
        del update_data["is_trusted"]

    # Section access control — block locked sections for non-creators
    blocked = check_section_access(chat, update_data, is_creator)
    if blocked:
        for field in blocked:
            del update_data[field]

    # settings_locked_sections — only creator can change
    if "settings_locked_sections" in update_data and not is_creator:
        del update_data["settings_locked_sections"]

    if update_data:
        await record_settings_changes(session, chat, user.id, update_data)
        chat = await update_chat_settings(session, chat_id, **update_data)

    response = ChatFullSettingsResponse.model_validate(chat)
    response.is_creator = is_creator
    return response


@router.get("/{chat_id}/audit-log")
async def get_chat_audit_log(
    chat_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_authenticated_user)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> PaginatedResponse[AuditLogEntry]:
    """Получить лог изменений настроек чата."""
    await require_chat_admin(user, chat_id)

    entries, total = await get_audit_log(session, chat_id, page, limit)
    total_pages = (total + limit - 1) // limit

    return PaginatedResponse(
        items=[AuditLogEntry.model_validate(e) for e in entries],
        pagination=Pagination(
            page=page,
            limit=limit,
            total=total,
            total_pages=total_pages,
        ),
    )


@router.get("", response_model=PaginatedResponse[ChatResponse])
async def list_chats(
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    query: str | None = None,
    include_private: bool = Query(False),
    sort_by: str = Query("created_at", pattern="^(created_at|updated_at|title|id|users_count|triggers_count)$"),
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
    for chat, banned_chat, triggers_count, users_count in results:
        item = ChatResponse.model_validate(chat)
        item.triggers_count = triggers_count
        item.users_count = users_count
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
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    if not chat.photo_id:
        try:
            tg_chat = await bot.get_chat(chat_id)
            if tg_chat.photo:
                chat.photo_id = tg_chat.photo.big_file_id
                await session.commit()
                await session.refresh(chat)
            else:
                raise HTTPException(status_code=404, detail="Photo not found")
        except Exception as e:
            raise HTTPException(status_code=404, detail="Photo not found") from e

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


@router.patch("/{chat_id}/settings", response_model=ChatResponse)
async def update_chat_settings_endpoint(
    chat_id: int,
    request: UpdateChatSettingsRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
) -> ChatResponse:
    """Обновить настройки чата."""
    chat, banned_chat = await get_chat_with_ban_status(session, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    chat = await update_chat_settings_specific(
        session,
        chat_id,
        timezone=request.timezone,
        module_triggers=request.module_triggers,
        module_moderation=request.module_moderation,
    )

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
    status: str | None = Query(None, pattern="^(pending|safe|flagged|banned|all)$"),
    search: str | None = None,
    sort_by: str = Query("created_at", pattern="^(created_at|key_phrase)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
) -> PaginatedResponse[TriggerResponse]:
    """Получить триггеры чата."""
    triggers, total = await get_triggers_filtered(
        session,
        page=page,
        limit=limit,
        status=status,
        search=search,
        chat_id=chat_id,
        sort_by=sort_by,
        order=order,
    )
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
