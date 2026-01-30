import logging

from app.core.broker import broker
from app.core.database import engine
from app.core.logging import setup_logging
from app.core.tasks import update_gban_task
from app.db.models.moderation_history import ModerationStep
from app.db.models.trigger import Trigger
from app.schemas.moderation import TriggerModerationTask
from app.services.moderation_history_service import add_history_step
from app.worker import captcha, message
from app.worker.llm import call_moderation_model
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
    scheduler.start()


@app.after_shutdown
async def stop_scheduler() -> None:
    """Остановка планировщика задач."""
    logger.info("Stopping scheduler...")
    scheduler.shutdown()


@broker.subscriber("q.moderation.analyze")
async def analyze_trigger(task: TriggerModerationTask) -> None:
    logger.info(f"Analyzing trigger {task.trigger_id} from chat {task.chat_id}")

    async with async_session() as session:
        await add_history_step(session, task.trigger_id, ModerationStep.PROCESSING_STARTED)
        await session.commit()

        # 1. Process media (photo/video)
        image_description = ""
        if task.file_id and task.file_type:
            await add_history_step(session, task.trigger_id, ModerationStep.MEDIA_PROCESSING)
            await session.commit()

            image_description = await process_media(task)

            await add_history_step(
                session,
                task.trigger_id,
                ModerationStep.MEDIA_PROCESSED,
                details={"has_description": bool(image_description)},
            )
            await session.commit()

            if image_description:
                await add_history_step(
                    session,
                    task.trigger_id,
                    ModerationStep.VISION_COMPLETED,
                    details={"description_preview": image_description[:100]},
                )
                await session.commit()

        # 2. Call Moderation Model
        await add_history_step(session, task.trigger_id, ModerationStep.TEXT_ANALYZING)
        await session.commit()

        result = await call_moderation_model(task.text_content, task.caption, image_description)

        await add_history_step(
            session,
            task.trigger_id,
            ModerationStep.TEXT_COMPLETED,
            details={"category": result.category if result else "error"},
        )
        await session.commit()

        # 3. Update Database
        trigger = await session.get(Trigger, task.trigger_id)
        if not trigger:
            logger.warning(f"Trigger {task.trigger_id} not found")
            return

        await handle_moderation_result(session, trigger, result, image_description)
