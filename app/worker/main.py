import asyncio
import logging
import time

from app.core.broker import broker
from app.core.config import settings
from app.core.database import engine
from app.core.logging import setup_logging
from app.core.tasks import update_gban_task
from app.core.valkey import valkey
from app.db.models.moderation_history import ModerationStep
from app.db.models.trigger import Trigger
from app.schemas.moderation import ModerationLLMResult, TriggerModerationTask
from app.services.moderation_history_service import add_history_step
from app.services.reputation_cleanup import cleanup_old_logs
from app.services.stuck_moderation import requeue_stuck_triggers
from app.services.tag_recalculation import recalculate_chat_tags
from app.services.trigger_service import clear_processing_status, set_processing_status
from app.worker import captcha, message
from app.worker.http import close_session
from app.worker.links import build_link_context
from app.worker.llm import InferenceUnavailableError, moderate, strip_usernames
from app.worker.service import handle_moderation_result, moderation_skip_reason, process_media
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from faststream import AckPolicy, FastStream
from faststream.rabbit import RabbitQueue
from faststream.rabbit.annotations import RabbitMessage
from faststream.rabbit.schemas.channel import Channel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

__all__ = ("captcha", "message")


setup_logging()

logger = logging.getLogger(__name__)

app = FastStream(broker)
scheduler = AsyncIOScheduler()

async_session = async_sessionmaker(engine, expire_on_commit=False)

MODERATION_ATTEMPTS_TTL = 86400  # сутки — тот же паттерн TTL, что у set_processing_status


async def increment_moderation_attempts(trigger_id: int) -> int:
    """Увеличить и продлить TTL счётчик неудачных попыток модерации триггера.

    Универсальная защита от бесконечного retry на 'ядовитом' сообщении (см.
    MODERATION_MAX_ATTEMPTS в app/core/config.py): даже когда moderate() раз за
    разом бросает InferenceUnavailableError (в т.ч. по причинам, которые часть 1
    не отличает от 'модель не смогла'), сообщение рано или поздно перестаёт
    возвращаться в очередь и не блокирует её вечно с prefetch_count=1.
    """
    key = f"moderation_attempts:{trigger_id}"
    attempts = await valkey.incr(key)
    await valkey.expire(key, MODERATION_ATTEMPTS_TTL)
    return attempts


async def reset_moderation_attempts(trigger_id: int) -> None:
    """Сбросить счётчик попыток модерации триггера — обработка завершилась без nack."""
    await valkey.delete(f"moderation_attempts:{trigger_id}")


@app.after_startup
async def start_scheduler() -> None:
    """Запуск планировщика задач."""
    logger.info("Starting scheduler...")
    scheduler.add_job(update_gban_task)
    scheduler.add_job(update_gban_task, "interval", hours=1)
    scheduler.add_job(cleanup_old_logs, "cron", hour=3, minute=0)
    scheduler.add_job(requeue_stuck_triggers, "interval", minutes=10)
    scheduler.start()


@app.after_shutdown
async def stop_scheduler() -> None:
    """Остановка планировщика задач и HTTP-сессии."""
    logger.info("Stopping scheduler...")
    scheduler.shutdown()
    await close_session()


async def _finish_skipped(
    session: AsyncSession,
    task: TriggerModerationTask,
    msg: RabbitMessage,
    skip_reason: str,
) -> None:
    """Завершить задачу, которую модерировать уже незачем: ack и уборка.

    Вызывается из всех точек, где обнаружено, что триггер удалён, чат забанен или
    неактивен. Сообщение подтверждается, а не возвращается в очередь: причина не
    рассосётся сама, а с prefetch_count=1 такое сообщение держит всю очередь.
    """
    # При полностью удалённом триггере (не soft-deleted) не пишем историю:
    # FK на triggers.id нет, запись упадёт. Для soft-deleted — запись допустима.
    trigger_row = await session.get(Trigger, task.trigger_id)
    if trigger_row is not None:
        await add_history_step(
            session,
            task.trigger_id,
            ModerationStep.SKIPPED,
            details={"reason": skip_reason},
        )
        await session.commit()
    await clear_processing_status(task.trigger_id)
    await reset_moderation_attempts(task.trigger_id)
    if task.silent:
        await valkey.hincrby("bulk_remoderate_progress", "processed", 1)
    await msg.ack()


@broker.subscriber(
    RabbitQueue("q.moderation.analyze", durable=True),
    channel=Channel(prefetch_count=1),
    ack_policy=AckPolicy.MANUAL,
)
async def analyze_trigger(task: TriggerModerationTask, msg: RabbitMessage) -> None:
    logger.info("Analyzing trigger %d from chat %d", task.trigger_id, task.chat_id)

    # Освежаем processing-маркер: при backlog'е сообщение может ждать в очереди
    # дольше первичного TTL set_processing_status, иначе UI решит, что триггер
    # 'застрял'. Как только worker дошёл -- продлеваем на полный TTL.
    await set_processing_status(task.trigger_id)

    async with async_session() as session:
        skip_reason = await moderation_skip_reason(session, task.trigger_id)
        if skip_reason:
            logger.info("Trigger %d: skip moderation (%s)", task.trigger_id, skip_reason)
            await _finish_skipped(session, task, msg, skip_reason)
            return

        await add_history_step(session, task.trigger_id, ModerationStep.PROCESSING_STARTED)
        await session.commit()

        # 1. Process media (JPEG for vision) + transcribe speech (voice/video_note)
        image_bytes: bytes | None = None
        transcript: str = ""
        if task.file_id and task.file_type:
            await add_history_step(session, task.trigger_id, ModerationStep.MEDIA_PROCESSING)
            await session.commit()

            media = await process_media(task)
            image_bytes = media.image
            transcript = (media.transcript or "").strip()

            await add_history_step(
                session,
                task.trigger_id,
                ModerationStep.MEDIA_PROCESSED,
                details={"has_image": image_bytes is not None},
            )
            await session.commit()

            if transcript or media.asr is not None:
                await add_history_step(
                    session,
                    task.trigger_id,
                    ModerationStep.TRANSCRIBED,
                    details={"transcript": transcript, **(media.asr or {})},
                )
                await session.commit()

        # 2. Собираем link-context из оригинальных text/caption (до strip):
        # @handles и URL из исходника резолвятся в get_chat/safe_fetch, результат
        # прокидывается в промпт. После этого стрипаем @username из основного текста —
        # маленькие модели ловятся на подстроки внутри handle, а смысловой контент
        # уже вынут в link_context.
        text_for_llm = (task.text_content or "").strip()
        caption_for_llm = (task.caption or "").strip()
        try:
            link_context, redirect_chains = await build_link_context(text_for_llm, caption_for_llm)
        except Exception as e:
            logger.warning("Trigger %d: build_link_context failed, degrading gracefully: %s", task.trigger_id, e)
            link_context, redirect_chains = "", []
        redirect_chain = redirect_chains[0] if redirect_chains else None
        text_for_llm = strip_usernames(text_for_llm).strip()
        caption_for_llm = strip_usernames(caption_for_llm).strip()
        has_llm_content = bool(image_bytes or transcript or text_for_llm or caption_for_llm or link_context)
        # llm_used прокидывается в handle_moderation_result -- bypass-исход (ниже) не должен
        # накручивать стрик доверия чата (см. defect #1 ревью): иначе участник чата бесплатно
        # создаёт 20 пустых триггеров и обходит LLM-модерацию следующих вредоносных.
        llm_used = has_llm_content
        if not has_llm_content:
            logger.info("Trigger %d: bypass AI (no moderatable content)", task.trigger_id)
            result: ModerationLLMResult | None = ModerationLLMResult(
                category="Safe",
                confidence=1.0,
                reasoning="Нет распознаваемого содержания для модерации, AI-модерация пропущена.",
            )
        else:
            # Перепроверка перед самым дорогим шагом: между первой проверкой и этим местом
            # прошли скачивание медиа, извлечение кадров и ASR -- это минуты, за которые
            # триггер могли удалить, а чат забанить. Незачем занимать GPU и слот семафора.
            skip_reason = await moderation_skip_reason(session, task.trigger_id)
            if skip_reason:
                logger.info("Trigger %d: skip before inference (%s)", task.trigger_id, skip_reason)
                await _finish_skipped(session, task, msg, skip_reason)
                return

            # Call AI inference with retry
            await add_history_step(session, task.trigger_id, ModerationStep.AI_ANALYZING)
            await session.commit()

            result = None
            for attempt in range(3):
                try:
                    result = await moderate(
                        text=text_for_llm,
                        caption=caption_for_llm,
                        image=image_bytes,
                        link_context=link_context,
                        transcript=transcript,
                    )
                    break
                except InferenceUnavailableError:
                    logger.warning(
                        "GPU inference unavailable for trigger %d (attempt %d/3), waiting 30s",
                        task.trigger_id,
                        attempt + 1,
                    )
                    if attempt < 2:
                        await asyncio.sleep(30)
                    else:
                        # Инференс затянулся на все 3 попытки этого захода. Считаем
                        # попытки по trigger_id в Valkey (TTL сутки) — независимо от
                        # части 1 (различение форматной/серверной 500-ошибки), любая
                        # retryable-ошибка может повторяться бесконечно на 'ядовитом'
                        # контенте. Без лимита с prefetch_count=1 такое сообщение
                        # блокирует всю очередь модерации навсегда (см. инцидент).
                        attempts = await increment_moderation_attempts(task.trigger_id)
                        if attempts > settings.MODERATION_MAX_ATTEMPTS:
                            logger.error(
                                "Trigger %d exceeded MODERATION_MAX_ATTEMPTS (%d attempts > %d), "
                                "giving up on retry and flagging as AI error instead of nack",
                                task.trigger_id,
                                attempts,
                                settings.MODERATION_MAX_ATTEMPTS,
                            )
                            await reset_moderation_attempts(task.trigger_id)
                            trigger = await session.get(Trigger, task.trigger_id)
                            if not trigger:
                                logger.warning("Trigger %d not found", task.trigger_id)
                                await msg.ack()
                                return
                            await handle_moderation_result(
                                session,
                                trigger,
                                None,
                                silent=task.silent,
                                transcript=transcript,
                                redirect_chain=redirect_chain,
                                llm_used=False,
                            )
                            if task.silent:
                                bulk_key = "bulk_remoderate_progress"
                                await valkey.hincrby(bulk_key, "processed", 1)
                                await valkey.hincrby(bulk_key, "flagged", 1)
                            await msg.ack()
                            return

                        # Отдыхаем перед nack, иначе с prefetch_count=1 worker тут же
                        # возьмёт это же сообщение обратно и закрутит hot-loop из
                        # retry'ев. Постмодерация — потерпит, ничего не теряем.
                        logger.error(
                            "GPU inference failed after 3 attempts for trigger %d (attempt %d/%d), "
                            "backing off %ds then nack",
                            task.trigger_id,
                            attempts,
                            settings.MODERATION_MAX_ATTEMPTS,
                            settings.MODERATION_FAIL_BACKOFF_SECONDS,
                        )
                        await asyncio.sleep(settings.MODERATION_FAIL_BACKOFF_SECONDS)

                        # За время попыток и бэкоффа (минуты) триггер могли удалить, а чат
                        # забанить -- тогда возвращать сообщение в очередь незачем, оно лишь
                        # снова займёт единственный слот prefetch.
                        skip_reason = await moderation_skip_reason(session, task.trigger_id)
                        if skip_reason:
                            logger.info("Trigger %d: skip instead of requeue (%s)", task.trigger_id, skip_reason)
                            await _finish_skipped(session, task, msg, skip_reason)
                            return

                        await msg.nack()
                        return

            # Успешно получили ответ (или окончательное None, не требующее retry) —
            # счётчик попыток для этого триггера больше не нужен.
            await reset_moderation_attempts(task.trigger_id)

            await add_history_step(
                session,
                task.trigger_id,
                ModerationStep.AI_COMPLETED,
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

        await handle_moderation_result(
            session,
            trigger,
            result,
            silent=task.silent,
            transcript=transcript,
            redirect_chain=redirect_chain,
            llm_used=llm_used,
        )

        # Update bulk remoderation progress if running
        if task.silent:
            bulk_key = "bulk_remoderate_progress"
            await valkey.hincrby(bulk_key, "processed", 1)
            if result and result.category != "Safe":
                await valkey.hincrby(bulk_key, "flagged", 1)

        await msg.ack()


@broker.subscriber(RabbitQueue("q.tags.recalculate", durable=True))
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
