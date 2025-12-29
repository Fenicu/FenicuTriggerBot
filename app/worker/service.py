import logging

from app.core.broker import broker
from app.db.models.trigger import ModerationStatus, Trigger
from app.schemas.moderation import ModerationAlert, ModerationLLMResult, TriggerModerationTask
from app.worker.llm import call_vision_model
from app.worker.telegram import download_file, get_telegram_file_url
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def process_image(task: TriggerModerationTask) -> str:
    """Обработать изображение и получить описание."""
    if not task.file_id or task.file_type != "photo":
        return ""

    file_url = await get_telegram_file_url(task.file_id)
    if not file_url:
        return ""

    file_data = await download_file(file_url)
    if not file_data:
        return ""

    description = await call_vision_model(file_data)
    logger.info(f"Image description: {description}")
    return description


async def handle_moderation_result(session: AsyncSession, trigger: Trigger, result: ModerationLLMResult | None) -> None:
    """Обновить статус триггера на основе результата модерации."""
    if not result:
        trigger.moderation_status = ModerationStatus.FLAGGED
        trigger.moderation_reason = "AI Error"
        await session.commit()

        alert = ModerationAlert(
            trigger_id=trigger.id,
            chat_id=trigger.chat_id,
            category="Error",
            reasoning="AI failed to process",
        )
        await broker.publish(alert, "q.moderation.alerts")
        return

    if result.category == "Safe":
        trigger.moderation_status = ModerationStatus.SAFE
        trigger.moderation_reason = "Safe"
        await session.commit()
        logger.info(f"Trigger {trigger.id} marked as Safe. Reasoning: {result.reasoning}")
    else:
        trigger.moderation_status = ModerationStatus.FLAGGED
        trigger.moderation_reason = result.category
        await session.commit()

        alert = ModerationAlert(
            trigger_id=trigger.id,
            chat_id=trigger.chat_id,
            category=result.category,
            confidence=result.confidence,
            reasoning=result.reasoning,
        )
        await broker.publish(alert, "q.moderation.alerts")
        logger.info(f"Trigger {trigger.id} flagged as {result.category}. Reasoning: {result.reasoning}")
