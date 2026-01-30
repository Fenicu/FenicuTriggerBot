import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.valkey import valkey
from app.db.models.moderation_history import ModerationHistory, ModerationStep

logger = logging.getLogger(__name__)

SSE_CHANNEL_PREFIX = "moderation_history:"


async def add_history_step(
    session: AsyncSession,
    trigger_id: int,
    step: ModerationStep,
    details: dict | None = None,
    actor_id: int | None = None,
) -> ModerationHistory:
    """Добавить запись в историю модерации и уведомить подписчиков."""
    history = ModerationHistory(
        trigger_id=trigger_id,
        step=step.value,
        details=details,
        actor_id=actor_id,
    )
    session.add(history)
    await session.flush()
    await session.refresh(history)

    event_data = {
        "id": history.id,
        "trigger_id": trigger_id,
        "step": step.value,
        "details": details,
        "actor_id": actor_id,
        "created_at": history.created_at.isoformat(),
    }
    try:
        await valkey.publish(
            f"{SSE_CHANNEL_PREFIX}{trigger_id}",
            json.dumps(event_data),
        )
    except Exception as e:
        logger.warning(f"Failed to publish moderation history event: {e}")

    return history


async def get_history_by_trigger(
    session: AsyncSession,
    trigger_id: int,
) -> list[ModerationHistory]:
    """Получить всю историю модерации триггера."""
    stmt = (
        select(ModerationHistory)
        .where(ModerationHistory.trigger_id == trigger_id)
        .order_by(ModerationHistory.created_at.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def get_current_step(history: list[ModerationHistory]) -> str:
    """Определить текущий этап на основе истории."""
    if not history:
        return ModerationStep.CREATED.value
    return history[-1].step
