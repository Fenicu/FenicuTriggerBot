import logging

from app.core.broker import broker
from app.core.database import engine
from app.core.logging import setup_logging
from app.db.models.trigger import Trigger
from app.schemas.moderation import TriggerModerationTask
from app.worker import captcha, message

__all__ = ("captcha", "message")


from app.worker.llm import call_moderation_model
from app.worker.service import handle_moderation_result, process_image
from faststream import FastStream
from sqlalchemy.ext.asyncio import async_sessionmaker

setup_logging()

logger = logging.getLogger(__name__)

app = FastStream(broker)

async_session = async_sessionmaker(engine, expire_on_commit=False)


@broker.subscriber("q.moderation.analyze")
async def analyze_trigger(task: TriggerModerationTask) -> None:
    logger.info(f"Analyzing trigger {task.trigger_id} from chat {task.chat_id}")

    # 1. Process Image (if any)
    image_description = await process_image(task)

    # 2. Call Moderation Model
    result = await call_moderation_model(task.text_content, task.caption, image_description)

    # 3. Update Database
    async with async_session() as session:
        trigger = await session.get(Trigger, task.trigger_id)
        if not trigger:
            logger.warning(f"Trigger {task.trigger_id} not found")
            return

        await handle_moderation_result(session, trigger, result)
