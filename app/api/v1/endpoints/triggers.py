import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_admin_from_query
from app.core.database import get_db
from app.core.valkey import valkey
from app.db.models.chat import Chat
from app.db.models.trigger import Trigger
from app.db.models.user import User
from app.schemas.moderation import ModerationHistoryListResponse, ModerationHistoryRead
from app.schemas.trigger import TriggerListResponse, TriggerQueueStatus, TriggerRead, TriggerStatsResponse
from app.services.moderation_history_service import (
    SSE_CHANNEL_PREFIX,
    get_current_step,
    get_history_by_trigger,
)
from app.services.preview_service import generate_preview_url
from app.services.trigger_service import (
    approve_trigger,
    bulk_remoderate_safe,
    delete_trigger_by_id,
    get_processing_status,
    get_triggers_filtered,
    get_triggers_stats,
    requeue_trigger,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=TriggerListResponse)
async def get_triggers(
    session: Annotated[AsyncSession, Depends(get_db)],
    admin: Annotated[User, Depends(get_current_admin)],
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, pattern="^(pending|safe|flagged|banned|error|all)$"),
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
