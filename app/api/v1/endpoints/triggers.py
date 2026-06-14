import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_admin_from_query
from app.core.config import settings
from app.core.database import get_db
from app.core.valkey import valkey
from app.db.models.chat import Chat
from app.db.models.trigger import MatchType, Trigger
from app.db.models.user import User
from app.schemas.moderation import ModerationHistoryListResponse, ModerationHistoryRead
from app.schemas.trigger import TriggerCreate, TriggerListResponse, TriggerQueueStatus, TriggerRead, TriggerStatsResponse, TriggerUpdate
from app.services.moderation_history_service import (
    SSE_CHANNEL_PREFIX,
    get_current_step,
    get_history_by_trigger,
)
from app.services.preview_service import generate_preview_url
from app.services.rich_html import RichHtmlError, validate_rich_html
from app.services.template_service import validate_template
from app.services.trigger_service import (
    approve_trigger,
    bulk_remoderate_safe,
    create_trigger,
    delete_trigger_by_id,
    get_processing_status,
    get_trigger_by_id,
    get_triggers_filtered,
    get_triggers_stats,
    requeue_trigger,
    update_trigger,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _skip_moderation(admin: User) -> bool:
    """Проверить, нужно ли пропустить модерацию для данного администратора."""
    return admin.is_trusted or admin.is_bot_moderator or admin.id in settings.BOT_ADMINS


async def _validate_trigger_payload(
    key_phrase: str,
    content: dict,
    match_type: MatchType,
    is_template: bool,
    rich: bool,
) -> None:
    """Валидация полей триггера; поднимает HTTPException(422) при ошибке."""
    if match_type == MatchType.REGEXP:
        from app.services.trigger_service import validate_regex
        err = await validate_regex(key_phrase)
        if err:
            raise HTTPException(status_code=422, detail=err)

    text = content.get("text") or content.get("caption") or ""

    if is_template and text:
        try:
            validate_template(text)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

    if rich and text:
        try:
            validate_rich_html(text)
        except RichHtmlError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e


@router.post("", response_model=TriggerRead, status_code=201)
async def create_trigger_endpoint(
    payload: TriggerCreate,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
) -> TriggerRead:
    """Создать новый триггер."""
    # rich требует шаблонного рендера
    effective_template = payload.is_template or payload.rich

    chat = await session.get(Chat, payload.chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    await _validate_trigger_payload(
        payload.key_phrase,
        payload.content,
        payload.match_type,
        effective_template,
        payload.rich,
    )

    trigger = await create_trigger(
        session=session,
        chat_id=payload.chat_id,
        key_phrase=payload.key_phrase,
        content=payload.content,
        match_type=payload.match_type,
        is_case_sensitive=payload.is_case_sensitive,
        access_level=payload.access_level,
        created_by=admin.id,
        skip_moderation=_skip_moderation(admin),
        is_template=effective_template,
        rich=payload.rich,
    )

    trigger.preview_url = generate_preview_url(trigger.id)
    trigger.chat_title = chat.title if chat else None
    return trigger


@router.patch("/{trigger_id}", response_model=TriggerRead)
async def update_trigger_endpoint(
    trigger_id: int,
    payload: TriggerUpdate,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
) -> TriggerRead:
    """Обновить триггер."""
    existing = await get_trigger_by_id(session, trigger_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Trigger not found")

    # Берём только явно переданные поля, null-значения отбрасываем
    data = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}

    # Эффективные значения для валидации
    eff_key = data.get("key_phrase", existing.key_phrase)
    eff_content = data.get("content", existing.content)
    eff_match = data.get("match_type", existing.match_type)
    eff_rich = data.get("rich", existing.rich)
    eff_template = data.get("is_template", existing.is_template)

    # rich форсирует is_template
    if eff_rich:
        eff_template = True
        data["is_template"] = True

    await _validate_trigger_payload(eff_key, eff_content, eff_match, eff_template, eff_rich)

    trigger = await update_trigger(session, trigger_id, **data)

    # Переотправить на модерацию, если контент изменился и нет доверенного статуса
    if "content" in data and not _skip_moderation(admin):
        trigger = await requeue_trigger(session, trigger_id)

    chat = await session.get(Chat, trigger.chat_id)
    trigger.preview_url = generate_preview_url(trigger.id)
    trigger.chat_title = chat.title if chat else None
    return trigger


@router.get("", response_model=TriggerListResponse)
async def get_triggers(
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, pattern="^(pending|safe|flagged|deleted|banned_chat|all)$"),
    search: str | None = None,
    chat_id: int | None = None,
    sort_by: str = Query("created_at", pattern="^(created_at|key_phrase|usage_count)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    active_only: bool = Query(True),
) -> TriggerListResponse:
    """Получить список триггеров с фильтрацией."""
    items, total = await get_triggers_filtered(
        session,
        page=page,
        limit=limit,
        status=status,
        search=search,
        chat_id=chat_id,
        sort_by=sort_by,
        order=order,
        active_only=active_only,
    )
    return TriggerListResponse(items=items, total=total)


@router.get("/stats", response_model=TriggerStatsResponse)
async def get_trigger_stats(
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    active_only: bool = Query(True),
) -> TriggerStatsResponse:
    """Получить счётчики триггеров по статусам."""
    stats = await get_triggers_stats(session, active_only=active_only)
    return TriggerStatsResponse(**stats)


@router.get("/{trigger_id}", response_model=TriggerRead)
async def get_trigger(
    trigger_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
) -> TriggerRead:
    """Получить триггер по ID."""
    trigger = await session.get(Trigger, trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")
    chat = await session.get(Chat, trigger.chat_id)
    trigger.chat_title = chat.title if chat else None
    trigger.preview_url = generate_preview_url(trigger.id)
    return trigger


@router.get("/{trigger_id}/queue-status", response_model=TriggerQueueStatus)
async def get_trigger_queue_status(
    trigger_id: int,
    admin: Annotated[User, Depends(get_current_admin)],
) -> TriggerQueueStatus:
    """Проверить статус обработки триггера в очереди."""
    is_processing = await get_processing_status(trigger_id)
    return TriggerQueueStatus(is_processing=is_processing)


@router.post("/{trigger_id}/approve", response_model=TriggerRead)
async def approve_trigger_endpoint(
    trigger_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
) -> TriggerRead:
    """Одобрить триггер."""
    trigger = await approve_trigger(session, trigger_id, admin.id)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")
    chat = await session.get(Chat, trigger.chat_id)
    trigger.chat_title = chat.title if chat else None
    trigger.preview_url = generate_preview_url(trigger.id)
    return trigger


@router.post("/{trigger_id}/requeue", response_model=TriggerRead)
async def requeue_trigger_endpoint(
    trigger_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
) -> TriggerRead:
    """Отправить триггер на перепроверку."""
    trigger = await requeue_trigger(session, trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")
    chat = await session.get(Chat, trigger.chat_id)
    trigger.chat_title = chat.title if chat else None
    trigger.preview_url = generate_preview_url(trigger.id)
    return trigger


@router.delete("/{trigger_id}")
async def delete_trigger(
    trigger_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
) -> dict[str, str]:
    """Удалить триггер."""
    success = await delete_trigger_by_id(session, trigger_id)
    if not success:
        raise HTTPException(status_code=404, detail="Trigger not found")

    return {"status": "ok"}


@router.get("/{trigger_id}/moderation-history", response_model=ModerationHistoryListResponse)
async def get_trigger_moderation_history(
    trigger_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
) -> ModerationHistoryListResponse:
    """Получить историю модерации триггера."""
    trigger = await session.get(Trigger, trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")

    history = await get_history_by_trigger(session, trigger_id)
    current_step = get_current_step(history)

    items = [
        ModerationHistoryRead(
            id=h.id,
            trigger_id=h.trigger_id,
            step=h.step,
            details=h.details,
            actor_id=h.actor_id,
            created_at=h.created_at.isoformat(),
        )
        for h in history
    ]

    return ModerationHistoryListResponse(items=items, current_step=current_step)


async def moderation_history_stream(trigger_id: int) -> AsyncGenerator[str]:
    """Генератор SSE событий для истории модерации."""
    pubsub = valkey.pubsub()
    channel = f"{SSE_CHANNEL_PREFIX}{trigger_id}"

    await pubsub.subscribe(channel)

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=30)
            if message and message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                yield f"data: {data}\n\n"
            else:
                yield ": heartbeat\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()


@router.get("/{trigger_id}/moderation-history/stream")
async def stream_moderation_history(
    trigger_id: int,
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin_from_query)],
) -> StreamingResponse:
    """SSE endpoint для real-time обновлений истории модерации (auth через query params)."""
    trigger = await session.get(Trigger, trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail="Trigger not found")

    return StreamingResponse(
        moderation_history_stream(trigger_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/bulk/remoderate-safe")
async def start_bulk_remoderate(
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
) -> dict:
    """Отправить все Safe-триггеры на перемодерацию (без алертов)."""
    # Check if already running
    progress = await valkey.hgetall("bulk_remoderate_progress")
    if progress and progress.get("status") == "running":
        processed = int(progress.get("processed", 0))
        total = int(progress.get("total", 0))
        if processed < total:
            raise HTTPException(400, f"Bulk remoderation already running: {processed}/{total}")

    count = await bulk_remoderate_safe(session)
    return {"status": "started", "total": count}


@router.get("/bulk/remoderate-progress")
async def get_bulk_remoderate_progress(
    admin: Annotated[User, Depends(get_current_admin)],
) -> dict:
    """Получить прогресс bulk-перемодерации."""
    progress = await valkey.hgetall("bulk_remoderate_progress")
    if not progress:
        return {"status": "idle", "total": 0, "processed": 0, "flagged": 0}

    total = int(progress.get("total", 0))
    processed = int(progress.get("processed", 0))
    flagged = int(progress.get("flagged", 0))
    status = "completed" if processed >= total else progress.get("status", "running")

    return {
        "status": status,
        "total": total,
        "processed": processed,
        "flagged": flagged,
        "safe": processed - flagged,
    }
