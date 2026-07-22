import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.core.broker import broker
from app.core.valkey import valkey
from app.db.models.chat import BannedChat, Chat
from app.db.models.moderation_history import ModerationStep
from app.db.models.trigger import ModerationStatus, Trigger
from app.schemas.moderation import ModerationAlert, ModerationLLMResult, TriggerModerationTask
from app.services.moderation_history_service import add_history_step
from app.worker.asr import transcribe
from app.worker.image import (
    combine_frames_horizontal,
    extract_frames_from_video_path,
    resize_image,
)
from app.worker.telegram import download_file, download_file_to_path, get_telegram_file_url
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

VIDEO_TYPES = {"video", "video_note", "animation"}


@dataclass
class MediaResult:
    """Результат обработки медиа: картинка для vision-модели и/или транскрипт речи."""

    image: bytes | None = None
    transcript: str | None = None
    asr: dict | None = None  # {language, duration} для истории


async def moderation_skip_reason(session: AsyncSession, trigger_id: int) -> str | None:
    """Причина пропустить модерацию или None.

    Чат забанен/неактивен или триггер удалён/отсутствует — модерировать незачем
    (не тратим inference, не шлём alert).
    """
    trigger = await session.get(Trigger, trigger_id)
    if trigger is None or trigger.is_deleted:
        return "deleted"
    if await session.get(BannedChat, trigger.chat_id) is not None:
        return "banned"
    chat = await session.get(Chat, trigger.chat_id)
    if chat is not None and not chat.is_active:
        return "inactive"
    return None


async def process_media(task: TriggerModerationTask) -> MediaResult:
    """Обработать медиа: JPEG для vision (photo/video) и/или транскрипт (voice/video_note).

    audio (музыка) не обрабатывается. ASR-ошибки не роняют результат (transcript=None).
    """
    empty = MediaResult()
    if not task.file_id or not task.file_type:
        return empty
    if task.file_type not in ("photo", "sticker", "voice", *VIDEO_TYPES):
        return empty

    file_url = await get_telegram_file_url(task.file_id)
    if not file_url:
        logger.warning(f"Failed to get file URL for trigger {task.trigger_id}")
        return empty
    if file_url.lower().endswith(".tgs"):
        logger.warning(f"Skipping TGS sticker for trigger {task.trigger_id}")
        return empty

    # voice: только ASR, картинки нет
    if task.file_type == "voice":
        data = await download_file(file_url)
        if not data:
            logger.warning(f"Failed to download voice for trigger {task.trigger_id}")
            return empty
        return await _transcribe_media(data, "voice.oga")

    is_video = task.file_type in VIDEO_TYPES or (task.file_type == "sticker" and file_url.lower().endswith(".webm"))

    if is_video:
        with tempfile.TemporaryDirectory() as tmp_dir:
            video_path = Path(tmp_dir) / "video"
            if not await download_file_to_path(file_url, str(video_path)):
                logger.warning(f"Failed to download video for trigger {task.trigger_id}")
                return empty
            frames = await extract_frames_from_video_path(video_path)
            image = None
            if frames:
                combined = combine_frames_horizontal(frames) if len(frames) > 1 else frames[0]
                if combined:
                    image = await resize_image(combined, ensure_jpeg=True)
            # video_note — ещё и транскрипт из того же скачанного файла
            transcript_res = MediaResult()
            if task.file_type == "video_note":
                data = video_path.read_bytes()
                transcript_res = await _transcribe_media(data, "note.mp4")
            return MediaResult(image=image, transcript=transcript_res.transcript, asr=transcript_res.asr)

    # photo / webp-sticker
    data = await download_file(file_url)
    if not data:
        logger.warning(f"Failed to download file for trigger {task.trigger_id}")
        return empty
    image = await resize_image(data, ensure_jpeg=True)
    return MediaResult(image=image)


async def _transcribe_media(data: bytes, filename: str) -> MediaResult:
    """Прогнать байты через ASR, завернуть в MediaResult (image=None)."""
    res = await transcribe(data, filename)
    if res is None:
        return MediaResult()
    return MediaResult(transcript=res.transcript, asr={"language": res.language, "duration": res.duration})


async def handle_moderation_result(
    session: AsyncSession,
    trigger: Trigger,
    result: ModerationLLMResult | None,
    silent: bool = False,
    transcript: str = "",
    redirect_chain: list[str] | None = None,
) -> None:
    """Обновить статус триггера на основе результата модерации.

    If silent=True, don't publish alerts to moderation channel (bulk remoderation).
    """
    trigger_id = trigger.id
    chat_id = trigger.chat_id

    await valkey.delete(f"trigger_processing:{trigger_id}")

    if not result:
        trigger.moderation_status = ModerationStatus.FLAGGED
        trigger.moderation_reason = "AI Error"
        await add_history_step(
            session,
            trigger_id,
            ModerationStep.AUTO_ERROR,
            details={"error": "AI failed to process"},
        )
        await session.commit()
        await valkey.delete(f"triggers:{chat_id}")

        if not silent and await session.get(Trigger, trigger_id):
            alert = ModerationAlert(
                trigger_id=trigger_id,
                chat_id=chat_id,
                category="Error",
                reasoning="AI failed to process",
                transcript=transcript or None,
                redirect_chain=redirect_chain,
            )
            await broker.publish(alert, "q.moderation.alerts")
            await add_history_step(session, trigger_id, ModerationStep.ALERT_SENT)
            await session.commit()
        elif not await session.get(Trigger, trigger_id):
            logger.warning(f"Trigger {trigger_id} was deleted during moderation, skipping alert")
        return

    if result.category == "Safe":
        trigger.moderation_status = ModerationStatus.SAFE
        trigger.moderation_reason = result.reasoning
        trigger.moderation_category = result.category
        trigger.moderation_confidence = result.confidence
        await add_history_step(
            session,
            trigger_id,
            ModerationStep.AUTO_APPROVED,
            details={"reasoning": result.reasoning},
        )
        await session.commit()
        await valkey.delete(f"triggers:{chat_id}")
        logger.info(f"Trigger {trigger_id} marked as Safe. Reasoning: {result.reasoning}")
    else:
        trigger.moderation_status = ModerationStatus.FLAGGED
        trigger.moderation_reason = f"{result.category}: {result.reasoning}"
        trigger.moderation_category = result.category
        trigger.moderation_confidence = result.confidence
        await add_history_step(
            session,
            trigger_id,
            ModerationStep.AUTO_FLAGGED,
            details={
                "category": result.category,
                "confidence": result.confidence,
                "reasoning": result.reasoning,
            },
        )
        await session.commit()
        await valkey.delete(f"triggers:{chat_id}")

        if not silent and await session.get(Trigger, trigger_id):
            alert = ModerationAlert(
                trigger_id=trigger_id,
                chat_id=chat_id,
                category=result.category,
                confidence=result.confidence,
                reasoning=result.reasoning,
                transcript=transcript or None,
                redirect_chain=redirect_chain,
            )
            await broker.publish(alert, "q.moderation.alerts")
            await add_history_step(session, trigger_id, ModerationStep.ALERT_SENT)
            await session.commit()
        logger.info(f"Trigger {trigger_id} flagged as {result.category}. Reasoning: {result.reasoning}")
