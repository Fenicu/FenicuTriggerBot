"""Страховка от потери сообщений модерации в RabbitMQ.

Даже с durable-очередями и persistent-сообщениями (см. app/core/broker.py) сообщение
модерации можно потерять: сбой брокера, ручная чистка очереди, баг. Триггер в таком
случае навсегда остаётся в БД со статусом PENDING, а задачи на его модерацию в очереди
уже нет -- см. инцидент с триггерами 16081-16084. Периодический подбор находит такие
"осиротевшие" триггеры и возвращает их в очередь модерации.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.database import engine
from app.db.models.chat import BannedChat, Chat
from app.db.models.trigger import ModerationStatus, Trigger
from app.services.trigger_service import get_processing_status, requeue_trigger

logger = logging.getLogger(__name__)

async_session = async_sessionmaker(engine, expire_on_commit=False)

# Ограничение на прогон -- не заливать очередь модерации разом, если зависших триггеров
# оказалось много (например, после длительного сбоя).
STUCK_TRIGGERS_BATCH_LIMIT = 50


async def requeue_stuck_triggers() -> int:
    """Найти зависшие PENDING-триггеры и вернуть их в очередь модерации.

    Кандидат: moderation_status=PENDING, не удалён, создан раньше порога
    MODERATION_STUCK_AFTER_MINUTES, чат активен и не забанен (дешёво проверяется
    прямо в SQL, как в bulk_remoderate_safe) и нет активного processing-маркера
    в Valkey -- маркер означает, что триггер прямо сейчас обрабатывается воркером,
    трогать его не нужно.

    Не должна ронять планировщик исключением -- любая ошибка логируется, функция
    возвращает 0. Сбой requeue_trigger по одному триггеру не прерывает обработку
    остальных кандидатов пачки.
    """
    try:
        threshold = datetime.now(UTC) - timedelta(minutes=settings.MODERATION_STUCK_AFTER_MINUTES)

        async with async_session() as session:
            stmt = (
                select(Trigger.id)
                .join(Chat, Trigger.chat_id == Chat.id)
                .where(
                    Trigger.moderation_status == ModerationStatus.PENDING,
                    Trigger.is_deleted.is_(False),
                    Trigger.created_at <= threshold,
                    Chat.is_active.is_(True),
                    ~Trigger.chat_id.in_(select(BannedChat.chat_id)),
                )
                .order_by(Trigger.created_at)
                .limit(STUCK_TRIGGERS_BATCH_LIMIT)
            )
            candidate_ids = list((await session.execute(stmt)).scalars().all())

            requeued = 0
            for trigger_id in candidate_ids:
                if await get_processing_status(trigger_id):
                    continue
                try:
                    trigger = await requeue_trigger(session, trigger_id)
                except Exception:
                    logger.exception("Failed to requeue stuck trigger %d", trigger_id)
                    await session.rollback()
                    continue
                if trigger is not None:
                    requeued += 1

        logger.info(
            "Stuck moderation sweep: found %d candidates, requeued %d",
            len(candidate_ids),
            requeued,
        )
        return requeued
    except Exception:
        logger.exception("Stuck moderation sweep failed")
        return 0
