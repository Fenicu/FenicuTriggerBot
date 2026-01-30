import logging
import tempfile
from pathlib import Path

from app.core.broker import broker
from app.core.valkey import valkey
from app.db.models.trigger import ModerationStatus, Trigger
from app.schemas.moderation import ModerationAlert, ModerationLLMResult, TriggerModerationTask
from app.worker.image import extract_frame_from_video_path
from app.worker.llm import call_vision_model
from app.worker.telegram import download_file, download_file_to_path, get_telegram_file_url
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

VIDEO_TYPES = {"video", "video_note", "animation"}


async def process_media(task: TriggerModerationTask) -> str:
    """Обработать медиа (фото или видео) и получить описание."""
    if not task.file_id or not task.file_type:
        return ""

    if task.file_type not in ("photo", *VIDEO_TYPES):
        return ""

    file_url = await get_telegram_file_url(task.file_id)
    if not file_url:
        logger.warning(f"Failed to get file URL for trigger {task.trigger_id}")
        return ""

    # Для видео: потоковая загрузка на диск (экономия памяти)
    if task.file_type in VIDEO_TYPES:
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "video"
            if not await download_file_to_path(file_url, str(video_path)):
                logger.warning(f"Failed to download video for trigger {task.trigger_id}")
                return ""

            logger.info(f"Extracting frame from {task.file_type} for trigger {task.trigger_id}")
            image_data = await extract_frame_from_video_path(video_path, position=0.5)
            if not image_data:
                logger.warning(f"Failed to extract frame from video for trigger {task.trigger_id}")
                return ""
    else:
        # Для фото: загрузка в память (небольшой размер)
        image_data = await download_file(file_url)
        if not image_data:
            logger.warning(f"Failed to download file for trigger {task.trigger_id}")
            return ""

    description = await call_vision_model(image_data)
    if not description:
        logger.warning(f"Vision model returned empty description for trigger {task.trigger_id}")
    else:
        logger.info(f"Media description for trigger {task.trigger_id}: {description[:200]}...")
    return description


async def handle_moderation_result(
    session: AsyncSession,
    trigger: Trigger,
    result: ModerationLLMResult | None,
    image_description: str = "",
) -> None:
    """Обновить статус триггера на основе результата модерации."""
    trigger_id = trigger.id
    chat_id = trigger.chat_id

    await valkey.delete(f"trigger_processing:{trigger_id}")

    if not result:
        trigger.moderation_status = ModerationStatus.FLAGGED
        trigger.moderation_reason = "AI Error"
        await session.commit()
        await valkey.delete(f"triggers:{chat_id}")

        if await session.get(Trigger, trigger_id):
            alert = ModerationAlert(
                trigger_id=trigger_id,
                chat_id=chat_id,
                category="Error",
                reasoning="AI failed to process",
                image_description=image_description or None,
            )
            await broker.publish(alert, "q.moderation.alerts")
        else:
            logger.warning(f"Trigger {trigger_id} was deleted during moderation, skipping alert")
        return

    if result.category == "Safe":
        trigger.moderation_status = ModerationStatus.SAFE
        trigger.moderation_reason = result.reasoning
        await session.commit()
        await valkey.delete(f"triggers:{chat_id}")
        logger.info(f"Trigger {trigger_id} marked as Safe. Reasoning: {result.reasoning}")
    else:
        trigger.moderation_status = ModerationStatus.FLAGGED
        trigger.moderation_reason = f"{result.category}: {result.reasoning}"
        await session.commit()
        await valkey.delete(f"triggers:{chat_id}")

        if await session.get(Trigger, trigger_id):
            alert = ModerationAlert(
                trigger_id=trigger_id,
                chat_id=chat_id,
                category=result.category,
                confidence=result.confidence,
                reasoning=result.reasoning,
                image_description=image_description or None,
            )
            await broker.publish(alert, "q.moderation.alerts")
            logger.info(f"Trigger {trigger_id} flagged as {result.category}. Reasoning: {result.reasoning}")
        else:
            logger.warning(f"Trigger {trigger_id} was deleted during moderation, skipping alert")
