import asyncio
import logging
import time

from faststream import AckPolicy
from faststream.rabbit.annotations import RabbitMessage

from app.core.broker import broker
from app.core.config import settings
from app.core.database import engine
from app.core.logging import setup_logging
from app.core.tasks import update_gban_task
from app.core.valkey import valkey
from app.db.models.moderation_history import ModerationStep
from app.db.models.trigger import Trigger
from app.schemas.moderation import TriggerModerationTask
from app.services.moderation_history_service import add_history_step
from app.services.reputation_cleanup import cleanup_old_logs
from app.services.tag_recalculation import recalculate_chat_tags
from app.worker import captcha, message
from app.worker.llm import InferenceUnavailableError, moderate
from app.worker.service import handle_moderation_result, process_media
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from faststream import FastStream
from sqlalchemy.ext.asyncio import async_sessionmaker

__all__ = ("captcha", "message")


setup_logging()

logger = logging.getLogger(__name__)

app = FastStream(broker)
scheduler = AsyncIOScheduler()

async_session = async_sessionmaker(engine, expire_on_commit=False)


@app.after_startup
async def start_scheduler() -> None:
    """Запуск планировщика задач."""
    logger.info("Starting scheduler...")
    scheduler.add_job(update_gban_task)
    scheduler.add_job(update_gban_task, "interval", hours=1)
    scheduler.add_job(cleanup_old_logs, "cron", hour=3, minute=0)
    scheduler.start()


@app.after_shutdown
async def stop_scheduler() -> None:
    """Остановка планировщика задач."""
    logger.info("Stopping scheduler...")
    scheduler.shutdown()


@broker.subscriber("q.moderation.analyze", ack_policy=AckPolicy.MANUAL)
async def analyze_trigger(task: TriggerModerationTask, msg: RabbitMessage) -> None:
    logger.info("Analyzing trigger %d from chat %d", task.trigger_id, task.chat_id)

    async with async_session() as session:
        await add_history_step(session, task.trigger_id, ModerationStep.PROCESSING_STARTED)
        await session.commit()

        # 1. Process media (download, extract frame, resize to JPEG)
        image_bytes: bytes | None = None
        if task.file_id and task.file_type:
            await add_history_step(session, task.trigger_id, ModerationStep.MEDIA_PROCESSING)
            await session.commit()

            image_bytes = await process_media(task)

            await add_history_step(
                session, task.trigger_id, ModerationStep.MEDIA_PROCESSED,
                details={"has_image": image_bytes is not None},
            )
            await session.commit()

        # 2. Call AI inference with retry
        await add_history_step(session, task.trigger_id, ModerationStep.AI_ANALYZING)
        await session.commit()

        result = None
        for attempt in range(3):
            try:
                result = await moderate(
                    text=task.text_content or "",
                    caption=task.caption or "",
                    image=image_bytes,
                )
                break
            except InferenceUnavailableError:
                logger.warning(
                    "GPU inference unavailable for trigger %d (attempt %d/3), waiting 30s",
                    task.trigger_id, attempt + 1,
                )
                if attempt < 2:
                    await asyncio.sleep(30)
                else:
                    # All retries failed — nack message back to queue
                    logger.error("GPU inference failed after 3 attempts for trigger %d, nacking", task.trigger_id)
                    await msg.nack()
                    return

        await add_history_step(
            session, task.trigger_id, ModerationStep.AI_COMPLETED,
            details={
                "category": result.category if result else "error",
                "confidence": result.confidence if result else None,
                "reasoning": result.reasoning if result else None,
            },
        )
        await session.commit()

        # 3. Update database
        trigger = await session.get(Trigger, task.trigger_id)
        if not trigger:
            logger.warning("Trigger %d not found", task.trigger_id)
            await msg.ack()
            return

        await handle_moderation_result(session, trigger, result, silent=task.silent)

        # Update bulk remoderation progress if running
        if task.silent:
            bulk_key = "bulk_remoderate_progress"
            await valkey.hincrby(bulk_key, "processed", 1)
            if result and result.category != "Safe":
                await valkey.hincrby(bulk_key, "flagged", 1)

        await msg.ack()


@broker.subscriber("q.tags.recalculate")
async def handle_tag_recalculation(message: dict) -> None:
    """Пересчитать теги при изменении порогов/пресета. Дебаунс 5 секунд."""
    chat_id = message.get("chat_id")
    if not chat_id:
        return

    # Записать timestamp этого запроса в Valkey
    debounce_key = f"tags_recalc:{chat_id}"
    request_time = str(time.time())
    await valkey.set(debounce_key, request_time, ex=30)

    # Ждём 5 секунд — если за это время придёт новый запрос, он перезапишет ключ
    await asyncio.sleep(5)

    # Проверяем: наш ли запрос последний?
    current = await valkey.get(debounce_key)
    if current and current != request_time:
        logger.info("Skipping tag recalculation for chat %d (debounced)", chat_id)
        return

    logger.info("Recalculating tags for chat %d", chat_id)
    await recalculate_chat_tags(chat_id)
