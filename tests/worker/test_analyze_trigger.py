"""Tests for analyze_trigger — голосовые и кружки без распознавания речи, bypass, redirect_chain.

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


async def test_voice_with_caption_moderated_without_transcript(msg):
    """Голосовое с подписью: moderate() получает только подпись, шага TRANSCRIBED нет."""
    task = _make_task(file_type="voice", caption="голосовое")
    mock_result = MagicMock(category="Safe", confidence=0.9, reasoning="ok")

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch("app.worker.main.process_media", new_callable=AsyncMock, return_value=MediaResult(image=None)),
        patch("app.worker.main.build_link_context", new_callable=AsyncMock, return_value=("", [])),
        patch("app.worker.main.moderate", new_callable=AsyncMock, return_value=mock_result) as mock_moderate,
        patch("app.worker.main.add_history_step", new_callable=AsyncMock) as mock_history,
        patch("app.worker.main.handle_moderation_result", new_callable=AsyncMock) as mock_handle,
        patch("app.worker.main.valkey") as mock_valkey,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_valkey.hincrby = AsyncMock()
        mock_session_cls.return_value = _mock_session_cls_with(MagicMock())

        await analyze_trigger(task, msg)

    mock_moderate.assert_called_once()
    assert "transcript" not in mock_moderate.call_args.kwargs
    assert mock_moderate.call_args.kwargs["caption"] == "голосовое"
    assert "transcript" not in mock_handle.call_args.kwargs
    steps = [c.args[2] for c in mock_history.call_args_list]
    assert ModerationStep.TRANSCRIBED not in steps
    msg.ack.assert_called_once()


async def test_bypass_when_voice_has_no_other_content(msg):
    """Voice без текста/caption/link_context — модерировать нечего: bypass, moderate() не вызывается."""
    task = _make_task(file_type="voice", text_content=None, caption=None)

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch(
            "app.worker.main.process_media",
            new_callable=AsyncMock,
            return_value=MediaResult(image=None),
        ),
        patch("app.worker.main.build_link_context", new_callable=AsyncMock, return_value=("", [])),
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


async def test_redirect_chain_passed_to_handle_moderation_result(msg):
    """build_link_context вернул цепочку редиректа — она прокидывается в handle_moderation_result."""
    task = _make_task(file_id=None, file_type=None, text_content="see https://short.link/x")
    mock_result = MagicMock(category="Scam", confidence=0.9, reasoning="casino redirect")

    chain = ["https://short.link/x", "https://casino.example/reg"]

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch("app.worker.main.build_link_context", new_callable=AsyncMock, return_value=("Link ...", [chain])),
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
    assert mock_handle.call_args.kwargs["redirect_chain"] == chain


async def test_bypass_passes_llm_used_false_to_handle_moderation_result(msg):
    """Bypass (нет содержимого для LLM) -- handle_moderation_result получает llm_used=False.

    Иначе bypass-исход накручивает стрик доверия чата бесплатно (см. defect #1 ревью).
    """
    task = _make_task(file_type="voice", text_content=None, caption=None)

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch(
            "app.worker.main.process_media",
            new_callable=AsyncMock,
            return_value=MediaResult(image=None),
        ),
        patch("app.worker.main.build_link_context", new_callable=AsyncMock, return_value=("", [])),
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
    assert mock_handle.call_args.kwargs["llm_used"] is False


async def test_normal_path_passes_llm_used_true_to_handle_moderation_result(msg):
    """Обычный путь (moderate() реально вызван) -- handle_moderation_result получает llm_used=True."""
    task = _make_task()
    mock_result = MagicMock(category="Safe", confidence=0.9, reasoning="ok")

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch(
            "app.worker.main.process_media",
            new_callable=AsyncMock,
            return_value=MediaResult(image=b"\xff\xd8\xff"),
        ),
        patch("app.worker.main.moderate", new_callable=AsyncMock, return_value=mock_result) as mock_moderate,
        patch("app.worker.main.add_history_step", new_callable=AsyncMock),
        patch("app.worker.main.handle_moderation_result", new_callable=AsyncMock) as mock_handle,
        patch("app.worker.main.valkey") as mock_valkey,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_valkey.hincrby = AsyncMock()
        mock_session_cls.return_value = _mock_session_cls_with(MagicMock())

        await analyze_trigger(task, msg)

    mock_moderate.assert_called_once()
    mock_handle.assert_called_once()
    assert mock_handle.call_args.kwargs["llm_used"] is True


async def test_no_redirect_chain_passes_none_to_handle_moderation_result(msg):
    """build_link_context не нашёл редиректов — handle_moderation_result получает redirect_chain=None."""
    task = _make_task(file_id=None, file_type=None, text_content="hello world")
    mock_result = MagicMock(category="Safe", confidence=0.9, reasoning="ok")

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch("app.worker.main.build_link_context", new_callable=AsyncMock, return_value=("", [])),
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
    assert mock_handle.call_args.kwargs["redirect_chain"] is None
