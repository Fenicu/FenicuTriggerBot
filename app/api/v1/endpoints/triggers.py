import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.core.database import get_db
from app.db.models.user import User
from app.schemas.trigger import TriggerListResponse, TriggerQueueStatus, TriggerRead
from app.services.trigger_service import (
    approve_trigger,
    delete_trigger_by_id,
    get_processing_status,
    get_triggers_filtered,
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
    status: str | None = Query(None, pattern="^(pending|safe|flagged|all)$"),
    search: str | None = None,
    chat_id: int | None = None,
) -> TriggerListResponse:
    """Получить список триггеров с фильтрацией."""
    items, total = await get_triggers_filtered(
        session, page=page, limit=limit, status=status, search=search, chat_id=chat_id
    )
    return TriggerListResponse(items=items, total=total)


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
