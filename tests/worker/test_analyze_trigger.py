"""Tests for analyze_trigger — voice transcript feeding into moderation.

Мок-уровень (как test_skip_guard.py), без реального DB: patch'им process_media,
moderate, handle_moderation_result и session на уровне app.worker.main.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models.moderation_history import ModerationStep
from app.schemas.moderation import TriggerModerationTask
from app.worker.main import analyze_trigger
from app.worker.service import MediaResult


def _make_task(
    trigger_id: int = 1,
    chat_id: int = -100500,
    file_id: str | None = "file123",
    file_type: str | None = "voice",
    text_content: str | None = None,
    caption: str | None = None,
) -> TriggerModerationTask:
    return TriggerModerationTask(
        trigger_id=trigger_id,
        chat_id=chat_id,
        text_content=text_content,
        caption=caption,
        file_id=file_id,
        file_type=file_type,
        silent=False,
    )


@pytest.fixture
def msg():
    m = AsyncMock()
    m.ack = AsyncMock()
    m.nack = AsyncMock()
    return m


def _mock_session_cls_with(mock_trigger):
    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=mock_trigger)
    mock_session.commit = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


async def test_transcript_passed_to_moderate(msg):
    """process_media вернул MediaResult(transcript=...) — moderate() получает transcript=."""
    task = _make_task()
    mock_result = MagicMock(category="Safe", confidence=0.9, reasoning="ok")

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch(
            "app.worker.main.process_media",
            new_callable=AsyncMock,
            return_value=MediaResult(image=None, transcript="привет это тест", asr={"language": "ru", "duration": 2.1}),
        ),
        patch("app.worker.main.moderate", new_callable=AsyncMock, return_value=mock_result) as mock_moderate,
        patch("app.worker.main.add_history_step", new_callable=AsyncMock),
        patch("app.worker.main.handle_moderation_result", new_callable=AsyncMock),
        patch("app.worker.main.valkey") as mock_valkey,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_valkey.hincrby = AsyncMock()
        mock_session_cls.return_value = _mock_session_cls_with(MagicMock())

        await analyze_trigger(task, msg)

    mock_moderate.assert_called_once()
    assert mock_moderate.call_args.kwargs["transcript"] == "привет это тест"
    msg.ack.assert_called_once()


async def test_transcribed_step_written_with_transcript(msg):
    """Есть транскрипт — пишется history-шаг TRANSCRIBED с деталями transcript+asr."""
    task = _make_task()
    mock_result = MagicMock(category="Safe", confidence=0.9, reasoning="ok")

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch(
            "app.worker.main.process_media",
            new_callable=AsyncMock,
            return_value=MediaResult(image=None, transcript="hello", asr={"language": "en", "duration": 1.0}),
        ),
        patch("app.worker.main.moderate", new_callable=AsyncMock, return_value=mock_result),
        patch("app.worker.main.add_history_step", new_callable=AsyncMock) as mock_history,
        patch("app.worker.main.handle_moderation_result", new_callable=AsyncMock),
        patch("app.worker.main.valkey") as mock_valkey,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_valkey.hincrby = AsyncMock()
        mock_session_cls.return_value = _mock_session_cls_with(MagicMock())

        await analyze_trigger(task, msg)

    transcribed_calls = [c for c in mock_history.call_args_list if c.args[2] == ModerationStep.TRANSCRIBED]
    assert len(transcribed_calls) == 1
    details = transcribed_calls[0].kwargs["details"]
    assert details == {"transcript": "hello", "language": "en", "duration": 1.0}


async def test_transcribed_step_written_when_asr_present_but_empty_transcript(msg):
    """ASR отработал, но распознал пустую строку — шаг TRANSCRIBED всё равно пишется."""
    task = _make_task()
    mock_result = MagicMock(category="Safe", confidence=1.0, reasoning="bypass")

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch(
            "app.worker.main.process_media",
            new_callable=AsyncMock,
            return_value=MediaResult(image=None, transcript="", asr={"language": "ru", "duration": 0.5}),
        ),
        patch("app.worker.main.moderate", new_callable=AsyncMock, return_value=mock_result),
        patch("app.worker.main.add_history_step", new_callable=AsyncMock) as mock_history,
        patch("app.worker.main.handle_moderation_result", new_callable=AsyncMock),
        patch("app.worker.main.valkey") as mock_valkey,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_valkey.hincrby = AsyncMock()
        mock_session_cls.return_value = _mock_session_cls_with(MagicMock())

        await analyze_trigger(task, msg)

    transcribed_calls = [c for c in mock_history.call_args_list if c.args[2] == ModerationStep.TRANSCRIBED]
    assert len(transcribed_calls) == 1


async def test_transcribed_step_not_written_for_photo_without_asr(msg):
    """Обычное фото: transcript пуст и media.asr is None — шага TRANSCRIBED нет."""
    task = _make_task(file_type="photo")
    mock_result = MagicMock(category="Safe", confidence=0.9, reasoning="ok")

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch(
            "app.worker.main.process_media",
            new_callable=AsyncMock,
            return_value=MediaResult(image=b"\xff\xd8\xff", transcript=None, asr=None),
        ),
        patch("app.worker.main.moderate", new_callable=AsyncMock, return_value=mock_result),
        patch("app.worker.main.add_history_step", new_callable=AsyncMock) as mock_history,
        patch("app.worker.main.handle_moderation_result", new_callable=AsyncMock),
        patch("app.worker.main.valkey") as mock_valkey,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_valkey.hincrby = AsyncMock()
        mock_session_cls.return_value = _mock_session_cls_with(MagicMock())

        await analyze_trigger(task, msg)

    transcribed_calls = [c for c in mock_history.call_args_list if c.args[2] == ModerationStep.TRANSCRIBED]
    assert transcribed_calls == []


async def test_bypass_when_voice_empty_transcript_no_other_content(msg):
    """Voice без картинки, без транскрипта и без текста/caption/link_context — bypass, moderate() не вызывается."""
    task = _make_task(file_type="voice", text_content=None, caption=None)

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch(
            "app.worker.main.process_media",
            new_callable=AsyncMock,
            return_value=MediaResult(image=None, transcript="", asr=None),
        ),
        patch("app.worker.main.build_link_context", new_callable=AsyncMock, return_value=""),
        patch("app.worker.main.moderate", new_callable=AsyncMock) as mock_moderate,
        patch("app.worker.main.add_history_step", new_callable=AsyncMock),
        patch("app.worker.main.handle_moderation_result", new_callable=AsyncMock) as mock_handle,
        patch("app.worker.main.valkey") as mock_valkey,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_valkey.hincrby = AsyncMock()
        mock_session_cls.return_value = _mock_session_cls_with(MagicMock())

        await analyze_trigger(task, msg)

    mock_moderate.assert_not_called()
    mock_handle.assert_called_once()
    result_arg = mock_handle.call_args.args[2]
    assert result_arg.category == "Safe"
    msg.ack.assert_called_once()


async def test_no_bypass_when_transcript_present_without_text(msg):
    """Voice с непустым транскриптом, но без text/caption — bypass НЕ срабатывает, moderate() вызывается."""
    task = _make_task(file_type="voice", text_content=None, caption=None)

    mock_result = MagicMock(category="Safe", confidence=0.9, reasoning="ok")

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch(
            "app.worker.main.process_media",
            new_callable=AsyncMock,
            return_value=MediaResult(image=None, transcript="купи закладку", asr={"language": "ru", "duration": 3.0}),
        ),
        patch("app.worker.main.build_link_context", new_callable=AsyncMock, return_value=""),
        patch("app.worker.main.moderate", new_callable=AsyncMock, return_value=mock_result) as mock_moderate,
        patch("app.worker.main.add_history_step", new_callable=AsyncMock),
        patch("app.worker.main.handle_moderation_result", new_callable=AsyncMock),
        patch("app.worker.main.valkey") as mock_valkey,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_valkey.hincrby = AsyncMock()
        mock_session_cls.return_value = _mock_session_cls_with(MagicMock())

        await analyze_trigger(task, msg)

    mock_moderate.assert_called_once()
    assert mock_moderate.call_args.kwargs["transcript"] == "купи закладку"


async def test_transcript_passed_to_handle_moderation_result(msg):
    """transcript прокидывается дальше в handle_moderation_result (для будущего ModerationAlert)."""
    task = _make_task()
    mock_result = MagicMock(category="Safe", confidence=0.9, reasoning="ok")

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch(
            "app.worker.main.process_media",
            new_callable=AsyncMock,
            return_value=MediaResult(image=None, transcript="test speech", asr={"language": "en", "duration": 1.5}),
        ),
        patch("app.worker.main.moderate", new_callable=AsyncMock, return_value=mock_result),
        patch("app.worker.main.add_history_step", new_callable=AsyncMock),
        patch("app.worker.main.handle_moderation_result", new_callable=AsyncMock) as mock_handle,
        patch("app.worker.main.valkey") as mock_valkey,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_valkey.hincrby = AsyncMock()
        mock_session_cls.return_value = _mock_session_cls_with(MagicMock())

        await analyze_trigger(task, msg)

    mock_handle.assert_called_once()
    assert mock_handle.call_args.kwargs["transcript"] == "test speech"
