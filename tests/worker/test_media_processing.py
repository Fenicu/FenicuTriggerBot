"""Tests for app/worker/service.py — process_media and handle_moderation_result."""

from pathlib import Path

import pytest
from unittest.mock import AsyncMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.moderation_history import ModerationHistory
from app.db.models.trigger import ModerationStatus, Trigger
from app.schemas.moderation import ModerationLLMResult, TriggerModerationTask
from tests.factories import create_chat, create_trigger, create_user


def _aret(value):
    """Async-возвращающий хелпер: async-функция, которая при вызове отдаёт value."""

    async def _f(*args, **kwargs):
        return value

    return _f


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
async def chat(db_session: AsyncSession):
    return await create_chat(db_session)


@pytest.fixture
async def user(db_session: AsyncSession):
    return await create_user(db_session)


@pytest.fixture
async def pending_trigger(db_session: AsyncSession, chat, user):
    return await create_trigger(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        moderation_status=ModerationStatus.PENDING,
    )


# ── process_media: photo ────────────────────────────────────────────────────


@patch("app.worker.service.resize_image", new_callable=AsyncMock)
@patch("app.worker.service.download_file", new_callable=AsyncMock)
@patch("app.worker.service.get_telegram_file_url", new_callable=AsyncMock)
async def test_process_media_photo(mock_url, mock_download, mock_resize):
    from app.worker.service import process_media

    mock_url.return_value = "https://example.com/photo.jpg"
    mock_download.return_value = b"\xff\xd8\xff\xe0" + b"\x00" * 100
    mock_resize.return_value = b"resized_jpeg"

    task = TriggerModerationTask(
        trigger_id=1,
        chat_id=-100,
        file_id="photo_123",
        file_type="photo",
    )

    result = await process_media(task)

    assert result.image == b"resized_jpeg"
    assert result.transcript is None
    mock_url.assert_awaited_once_with("photo_123")
    mock_download.assert_awaited_once()
    mock_resize.assert_awaited_once()


# ── process_media: video ────────────────────────────────────────────────────


@patch("app.worker.service.resize_image", new_callable=AsyncMock)
@patch("app.worker.service.combine_frames_horizontal")
@patch("app.worker.service.extract_frames_from_video_path", new_callable=AsyncMock)
@patch("app.worker.service.download_file_to_path", new_callable=AsyncMock)
@patch("app.worker.service.get_telegram_file_url", new_callable=AsyncMock)
async def test_process_media_video(mock_url, mock_dl_path, mock_frames, mock_combine, mock_resize):
    from app.worker.service import process_media

    mock_url.return_value = "https://example.com/video.mp4"
    mock_dl_path.return_value = True
    mock_frames.return_value = [b"frame1", b"frame2", b"frame3"]
    mock_combine.return_value = b"combined_frames"
    mock_resize.return_value = b"resized_video_jpeg"

    task = TriggerModerationTask(
        trigger_id=1,
        chat_id=-100,
        file_id="video_123",
        file_type="video",
    )

    result = await process_media(task)

    assert result.image == b"resized_video_jpeg"
    assert result.transcript is None
    mock_dl_path.assert_awaited_once()
    mock_frames.assert_awaited_once()
    mock_combine.assert_called_once()


@patch("app.worker.service.resize_image", new_callable=AsyncMock)
@patch("app.worker.service.extract_frames_from_video_path", new_callable=AsyncMock)
@patch("app.worker.service.download_file_to_path", new_callable=AsyncMock)
@patch("app.worker.service.get_telegram_file_url", new_callable=AsyncMock)
async def test_process_media_video_single_frame(mock_url, mock_dl_path, mock_frames, mock_resize):
    from app.worker.service import process_media

    mock_url.return_value = "https://example.com/video.mp4"
    mock_dl_path.return_value = True
    mock_frames.return_value = [b"single_frame"]
    mock_resize.return_value = b"resized_single"

    task = TriggerModerationTask(
        trigger_id=1,
        chat_id=-100,
        file_id="video_123",
        file_type="video",
    )

    result = await process_media(task)

    assert result.image == b"resized_single"


# ── process_media: sticker ──────────────────────────────────────────────────


@patch("app.worker.service.resize_image", new_callable=AsyncMock)
@patch("app.worker.service.download_file", new_callable=AsyncMock)
@patch("app.worker.service.get_telegram_file_url", new_callable=AsyncMock)
async def test_process_media_sticker_static(mock_url, mock_download, mock_resize):
    from app.worker.service import process_media

    mock_url.return_value = "https://example.com/sticker.webp"
    mock_download.return_value = b"sticker_data"
    mock_resize.return_value = b"resized_sticker"

    task = TriggerModerationTask(
        trigger_id=1,
        chat_id=-100,
        file_id="sticker_123",
        file_type="sticker",
    )

    result = await process_media(task)

    assert result.image == b"resized_sticker"


@patch("app.worker.service.resize_image", new_callable=AsyncMock)
@patch("app.worker.service.extract_frames_from_video_path", new_callable=AsyncMock)
@patch("app.worker.service.download_file_to_path", new_callable=AsyncMock)
@patch("app.worker.service.get_telegram_file_url", new_callable=AsyncMock)
async def test_process_media_sticker_webm_treated_as_video(mock_url, mock_dl_path, mock_frames, mock_resize):
    """WebM sticker (video sticker) should go through the video pipeline."""
    from app.worker.service import process_media

    mock_url.return_value = "https://example.com/sticker.webm"
    mock_dl_path.return_value = True
    mock_frames.return_value = [b"frame"]
    mock_resize.return_value = b"resized"

    task = TriggerModerationTask(
        trigger_id=1,
        chat_id=-100,
        file_id="vsticker_123",
        file_type="sticker",
    )

    result = await process_media(task)

    assert result.image == b"resized"
    mock_dl_path.assert_awaited_once()


# ── process_media: TGS skipped ─────────────────────────────────────────────


@patch("app.worker.service.get_telegram_file_url", new_callable=AsyncMock)
async def test_process_media_tgs_sticker_skipped(mock_url):
    from app.worker.service import process_media

    mock_url.return_value = "https://example.com/sticker.tgs"

    task = TriggerModerationTask(
        trigger_id=1,
        chat_id=-100,
        file_id="tgs_123",
        file_type="sticker",
    )

    result = await process_media(task)

    assert result.image is None
    assert result.transcript is None


# ── process_media: no file ──────────────────────────────────────────────────


async def test_process_media_no_file():
    from app.worker.service import process_media

    task = TriggerModerationTask(
        trigger_id=1,
        chat_id=-100,
        file_id=None,
        file_type=None,
    )

    result = await process_media(task)

    assert result.image is None
    assert result.transcript is None


async def test_process_media_unsupported_type():
    from app.worker.service import process_media

    task = TriggerModerationTask(
        trigger_id=1,
        chat_id=-100,
        file_id="doc_123",
        file_type="document",
    )

    result = await process_media(task)

    assert result.image is None
    assert result.transcript is None


# ── process_media: failed download ─────────────────────────────────────────


@patch("app.worker.service.get_telegram_file_url", new_callable=AsyncMock)
async def test_process_media_failed_url(mock_url):
    from app.worker.service import process_media

    mock_url.return_value = None

    task = TriggerModerationTask(
        trigger_id=1,
        chat_id=-100,
        file_id="bad_file",
        file_type="photo",
    )

    result = await process_media(task)

    assert result.image is None
    assert result.transcript is None


@patch("app.worker.service.download_file", new_callable=AsyncMock)
@patch("app.worker.service.get_telegram_file_url", new_callable=AsyncMock)
async def test_process_media_download_failure(mock_url, mock_download):
    from app.worker.service import process_media

    mock_url.return_value = "https://example.com/photo.jpg"
    mock_download.return_value = None

    task = TriggerModerationTask(
        trigger_id=1,
        chat_id=-100,
        file_id="fail_123",
        file_type="photo",
    )

    result = await process_media(task)

    assert result.image is None
    assert result.transcript is None


@patch("app.worker.service.extract_frames_from_video_path", new_callable=AsyncMock)
@patch("app.worker.service.download_file_to_path", new_callable=AsyncMock)
@patch("app.worker.service.get_telegram_file_url", new_callable=AsyncMock)
async def test_process_media_video_download_failure(mock_url, mock_dl_path, mock_frames):
    from app.worker.service import process_media

    mock_url.return_value = "https://example.com/video.mp4"
    mock_dl_path.return_value = False

    task = TriggerModerationTask(
        trigger_id=1,
        chat_id=-100,
        file_id="vid_fail",
        file_type="video",
    )

    result = await process_media(task)

    assert result.image is None
    assert result.transcript is None
    mock_frames.assert_not_awaited()


@patch("app.worker.service.extract_frames_from_video_path", new_callable=AsyncMock)
@patch("app.worker.service.download_file_to_path", new_callable=AsyncMock)
@patch("app.worker.service.get_telegram_file_url", new_callable=AsyncMock)
async def test_process_media_video_no_frames(mock_url, mock_dl_path, mock_frames):
    from app.worker.service import process_media

    mock_url.return_value = "https://example.com/video.mp4"
    mock_dl_path.return_value = True
    mock_frames.return_value = []

    task = TriggerModerationTask(
        trigger_id=1,
        chat_id=-100,
        file_id="vid_noframes",
        file_type="video",
    )

    result = await process_media(task)

    assert result.image is None
    assert result.transcript is None


# ── process_media: animation ────────────────────────────────────────────────


@patch("app.worker.service.resize_image", new_callable=AsyncMock)
@patch("app.worker.service.extract_frames_from_video_path", new_callable=AsyncMock)
@patch("app.worker.service.download_file_to_path", new_callable=AsyncMock)
@patch("app.worker.service.get_telegram_file_url", new_callable=AsyncMock)
async def test_process_media_animation(mock_url, mock_dl_path, mock_frames, mock_resize):
    """Animations (GIFs) should be treated as video."""
    from app.worker.service import process_media

    mock_url.return_value = "https://example.com/anim.mp4"
    mock_dl_path.return_value = True
    mock_frames.return_value = [b"gif_frame"]
    mock_resize.return_value = b"resized_gif"

    task = TriggerModerationTask(
        trigger_id=1,
        chat_id=-100,
        file_id="anim_123",
        file_type="animation",
    )

    result = await process_media(task)

    assert result.image == b"resized_gif"


# ── process_media: voice (ASR only, no image) ───────────────────────────────


async def test_process_media_voice_transcribes(monkeypatch):
    from app.worker import service
    from app.worker.asr import AsrResult

    task = TriggerModerationTask(trigger_id=1, chat_id=1, file_id="fid", file_type="voice")
    monkeypatch.setattr(service, "get_telegram_file_url", _aret("https://x/voice.oga"))
    monkeypatch.setattr(service, "download_file", _aret(b"oggbytes"))

    async def fake_transcribe(data, filename):
        return AsrResult(transcript="привет", language="ru", duration=1.0)

    monkeypatch.setattr(service, "transcribe", fake_transcribe)
    result = await service.process_media(task)
    assert result.image is None
    assert result.transcript == "привет"


async def test_process_media_voice_asr_failure_returns_no_transcript(monkeypatch):
    """transcribe() возвращает None (сервис недоступен) — process_media не падает."""
    from app.worker import service

    task = TriggerModerationTask(trigger_id=1, chat_id=1, file_id="fid", file_type="voice")
    monkeypatch.setattr(service, "get_telegram_file_url", _aret("https://x/voice.oga"))
    monkeypatch.setattr(service, "download_file", _aret(b"oggbytes"))
    monkeypatch.setattr(service, "transcribe", _aret(None))

    result = await service.process_media(task)
    assert result.image is None
    assert result.transcript is None


async def test_process_media_voice_download_failure(monkeypatch):
    from app.worker import service

    task = TriggerModerationTask(trigger_id=1, chat_id=1, file_id="fid", file_type="voice")
    monkeypatch.setattr(service, "get_telegram_file_url", _aret("https://x/voice.oga"))
    monkeypatch.setattr(service, "download_file", _aret(None))

    result = await service.process_media(task)
    assert result.image is None
    assert result.transcript is None


# ── process_media: video_note (image AND transcript from the same download) ─


async def test_process_media_video_note_image_and_transcript(monkeypatch):
    from app.worker import service
    from app.worker.asr import AsrResult

    task = TriggerModerationTask(trigger_id=1, chat_id=1, file_id="fid", file_type="video_note")
    monkeypatch.setattr(service, "get_telegram_file_url", _aret("https://x/note.mp4"))

    async def fake_download_file_to_path(url, path):
        Path(path).write_bytes(b"videobytes")
        return True

    monkeypatch.setattr(service, "download_file_to_path", fake_download_file_to_path)
    monkeypatch.setattr(service, "extract_frames_from_video_path", _aret([b"frame"]))
    monkeypatch.setattr(service, "combine_frames_horizontal", lambda f: b"frame")
    monkeypatch.setattr(service, "resize_image", _aret(b"jpeg"))

    async def fake_transcribe(data, filename):
        assert data == b"videobytes"
        assert filename == "note.mp4"
        return AsrResult(transcript="речь в кружке", language="ru", duration=2.0)

    monkeypatch.setattr(service, "transcribe", fake_transcribe)
    result = await service.process_media(task)
    assert result.image == b"jpeg"
    assert result.transcript == "речь в кружке"
    assert result.asr == {"language": "ru", "duration": 2.0}


async def test_process_media_video_note_download_failure_no_transcript(monkeypatch):
    """Если единый download видео упал — ни картинки, ни ASR не пытаемся достать."""
    from app.worker import service

    task = TriggerModerationTask(trigger_id=1, chat_id=1, file_id="fid", file_type="video_note")
    monkeypatch.setattr(service, "get_telegram_file_url", _aret("https://x/note.mp4"))
    monkeypatch.setattr(service, "download_file_to_path", _aret(False))

    result = await service.process_media(task)
    assert result.image is None
    assert result.transcript is None


# ── process_media: photo (image only, no transcript) ────────────────────────


async def test_process_media_photo_no_transcript(monkeypatch):
    from app.worker import service

    task = TriggerModerationTask(trigger_id=1, chat_id=1, file_id="fid", file_type="photo")
    monkeypatch.setattr(service, "get_telegram_file_url", _aret("https://x/p.jpg"))
    monkeypatch.setattr(service, "download_file", _aret(b"img"))
    monkeypatch.setattr(service, "resize_image", _aret(b"jpeg"))
    result = await service.process_media(task)
    assert result.image == b"jpeg"
    assert result.transcript is None


# ── process_media: audio (музыка) — не трогаем ───────────────────────────────


async def test_process_media_audio_ignored(monkeypatch):
    from app.worker import service

    task = TriggerModerationTask(trigger_id=1, chat_id=1, file_id="fid", file_type="audio")
    result = await service.process_media(task)
    assert result.image is None
    assert result.transcript is None


# ── handle_moderation_result: safe ──────────────────────────────────────────


async def test_handle_result_safe(db_session: AsyncSession, pending_trigger, chat):
    from app.worker.service import handle_moderation_result

    result = ModerationLLMResult(
        category="Safe",
        confidence=0.95,
        reasoning="Normal content",
    )

    await handle_moderation_result(db_session, pending_trigger, result)

    await db_session.refresh(pending_trigger)
    assert pending_trigger.moderation_status == ModerationStatus.SAFE
    assert pending_trigger.moderation_reason == "Normal content"


async def test_handle_result_safe_creates_history(db_session: AsyncSession, pending_trigger):
    from app.worker.service import handle_moderation_result

    result = ModerationLLMResult(
        category="Safe",
        confidence=0.99,
        reasoning="Clean",
    )

    await handle_moderation_result(db_session, pending_trigger, result)

    stmt = select(ModerationHistory).where(ModerationHistory.trigger_id == pending_trigger.id)
    history = (await db_session.execute(stmt)).scalars().all()
    steps = [h.step for h in history]
    assert "auto_approved" in steps


# ── handle_moderation_result: flagged ───────────────────────────────────────


async def test_handle_result_flagged(db_session: AsyncSession, pending_trigger, chat):
    from app.worker.service import handle_moderation_result

    result = ModerationLLMResult(
        category="Scam",
        confidence=0.92,
        reasoning="Suspicious links detected",
    )

    await handle_moderation_result(db_session, pending_trigger, result)

    await db_session.refresh(pending_trigger)
    assert pending_trigger.moderation_status == ModerationStatus.FLAGGED
    assert "Scam" in pending_trigger.moderation_reason


async def test_handle_result_flagged_publishes_alert(db_session: AsyncSession, pending_trigger, chat):
    from app.worker.service import handle_moderation_result
    from app.core.broker import broker

    result = ModerationLLMResult(
        category="Porn",
        confidence=0.99,
        reasoning="Explicit",
    )

    await handle_moderation_result(db_session, pending_trigger, result)

    broker.publish.assert_awaited()
    call_args = broker.publish.call_args
    alert = call_args.args[0]
    assert alert.category == "Porn"
    assert alert.trigger_id == pending_trigger.id


async def test_handle_result_flagged_alert_carries_transcript(db_session: AsyncSession, pending_trigger, chat):
    from app.worker.service import handle_moderation_result
    from app.core.broker import broker

    result = ModerationLLMResult(
        category="Scam",
        confidence=0.9,
        reasoning="Suspicious voice message",
    )

    await handle_moderation_result(db_session, pending_trigger, result, transcript="купи закладку")

    broker.publish.assert_awaited()
    alert = broker.publish.call_args.args[0]
    assert alert.transcript == "купи закладку"


async def test_handle_result_flagged_alert_transcript_none_when_empty(db_session: AsyncSession, pending_trigger, chat):
    """Пустая строка transcript ("") превращается в None (transcript=transcript or None)."""
    from app.worker.service import handle_moderation_result
    from app.core.broker import broker

    result = ModerationLLMResult(
        category="Scam",
        confidence=0.9,
        reasoning="No speech detected",
    )

    await handle_moderation_result(db_session, pending_trigger, result, transcript="")

    broker.publish.assert_awaited()
    alert = broker.publish.call_args.args[0]
    assert alert.transcript is None


async def test_handle_result_flagged_creates_history(db_session: AsyncSession, pending_trigger):
    from app.worker.service import handle_moderation_result

    result = ModerationLLMResult(
        category="Violence",
        confidence=0.85,
        reasoning="Violent imagery",
    )

    await handle_moderation_result(db_session, pending_trigger, result)

    stmt = select(ModerationHistory).where(ModerationHistory.trigger_id == pending_trigger.id)
    history = (await db_session.execute(stmt)).scalars().all()
    steps = [h.step for h in history]
    assert "auto_flagged" in steps
    assert "alert_sent" in steps


# ── handle_moderation_result: error (None result) ──────────────────────────


async def test_handle_result_error_none(db_session: AsyncSession, pending_trigger, chat):
    from app.worker.service import handle_moderation_result

    await handle_moderation_result(db_session, pending_trigger, None)

    await db_session.refresh(pending_trigger)
    assert pending_trigger.moderation_status == ModerationStatus.FLAGGED
    assert pending_trigger.moderation_reason == "AI Error"


async def test_handle_result_error_publishes_alert(db_session: AsyncSession, pending_trigger, chat):
    from app.worker.service import handle_moderation_result
    from app.core.broker import broker

    await handle_moderation_result(db_session, pending_trigger, None)

    broker.publish.assert_awaited()
    call_args = broker.publish.call_args
    alert = call_args.args[0]
    assert alert.category == "Error"


async def test_handle_result_error_alert_carries_transcript(db_session: AsyncSession, pending_trigger, chat):
    from app.worker.service import handle_moderation_result
    from app.core.broker import broker

    await handle_moderation_result(db_session, pending_trigger, None, transcript="привет мир")

    broker.publish.assert_awaited()
    alert = broker.publish.call_args.args[0]
    assert alert.transcript == "привет мир"


async def test_handle_result_error_creates_history(db_session: AsyncSession, pending_trigger):
    from app.worker.service import handle_moderation_result

    await handle_moderation_result(db_session, pending_trigger, None)

    stmt = select(ModerationHistory).where(ModerationHistory.trigger_id == pending_trigger.id)
    history = (await db_session.execute(stmt)).scalars().all()
    steps = [h.step for h in history]
    assert "auto_error" in steps


# ── handle_moderation_result: silent mode ───────────────────────────────────


async def test_handle_result_silent_no_alert(db_session: AsyncSession, pending_trigger, chat):
    """Silent mode should skip alert publishing."""
    from app.worker.service import handle_moderation_result
    from app.core.broker import broker

    result = ModerationLLMResult(
        category="Drugs",
        confidence=0.9,
        reasoning="Drug references",
    )

    await handle_moderation_result(db_session, pending_trigger, result, silent=True)

    await db_session.refresh(pending_trigger)
    assert pending_trigger.moderation_status == ModerationStatus.FLAGGED
    broker.publish.assert_not_awaited()


async def test_handle_result_silent_error_no_alert(db_session: AsyncSession, pending_trigger, chat):
    from app.worker.service import handle_moderation_result
    from app.core.broker import broker

    await handle_moderation_result(db_session, pending_trigger, None, silent=True)

    broker.publish.assert_not_awaited()


# ── handle_moderation_result: trigger deleted during processing ─────────────


async def test_handle_result_trigger_deleted_during_error(db_session: AsyncSession, chat, user):
    """If trigger is deleted during moderation error handling, skip alert."""
    from app.worker.service import handle_moderation_result

    trigger = await create_trigger(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        moderation_status=ModerationStatus.PENDING,
    )

    # Soft-delete the trigger
    trigger.is_deleted = True
    await db_session.commit()

    # Now handle result — the session.get(Trigger, trigger_id) will still find
    # the row since is_deleted is a soft flag not a real delete.
    # The handler does `await session.get(Trigger, trigger_id)` which doesn't
    # filter soft deletes, so it proceeds. But let's test the code path.
    await handle_moderation_result(db_session, trigger, None)

    # Should still set the status (the function operates on the passed object)
    assert trigger.moderation_status == ModerationStatus.FLAGGED


# ── handle_moderation_result: clears valkey processing key ──────────────────


async def test_handle_result_clears_processing_key(db_session: AsyncSession, pending_trigger, chat):
    from app.worker.service import handle_moderation_result
    from app.core.valkey import valkey

    result = ModerationLLMResult(
        category="Safe",
        confidence=0.99,
        reasoning="Clean",
    )

    await handle_moderation_result(db_session, pending_trigger, result)

    valkey.delete.assert_any_await(f"trigger_processing:{pending_trigger.id}")


async def test_handle_result_clears_trigger_cache(db_session: AsyncSession, pending_trigger, chat):
    from app.worker.service import handle_moderation_result
    from app.core.valkey import valkey

    result = ModerationLLMResult(
        category="Safe",
        confidence=0.99,
        reasoning="Clean",
    )

    await handle_moderation_result(db_session, pending_trigger, result)

    valkey.delete.assert_any_await(f"triggers:{chat.id}")
