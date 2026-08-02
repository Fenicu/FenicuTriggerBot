"""Tests for analyze_trigger — moderation retry-attempts limit (MODERATION_MAX_ATTEMPTS).

Универсальная защита от бесконечного retry на 'ядовитом' сообщении (см. инцидент
с триггером 16081): даже когда moderate() раз за разом кидает
InferenceUnavailableError, очередь q.moderation.analyze (prefetch_count=1) не
должна вставать навсегда. Мок-уровень, без реального DB — как test_analyze_trigger.py.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.config import settings
from app.schemas.moderation import TriggerModerationTask
from app.worker.llm import InferenceUnavailableError
from app.worker.main import analyze_trigger


def _make_task(
    trigger_id: int = 16081,
    chat_id: int = -100500,
    silent: bool = False,
    text_content: str | None = "test content",
) -> TriggerModerationTask:
    return TriggerModerationTask(
        trigger_id=trigger_id,
        chat_id=chat_id,
        text_content=text_content,
        caption=None,
        file_id=None,
        file_type=None,
        silent=silent,
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


async def test_max_attempts_exceeded_acks_without_nack_and_flags(msg):
    """Счётчик попыток превысил MODERATION_MAX_ATTEMPTS -- ack (не nack), триггер помечен ошибкой."""
    task = _make_task()

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch("app.worker.main.build_link_context", new_callable=AsyncMock, return_value=("", [])),
        patch("app.worker.main.moderate", new_callable=AsyncMock, side_effect=InferenceUnavailableError("boom")),
        patch("app.worker.main.asyncio.sleep", new_callable=AsyncMock),
        patch(
            "app.worker.main.increment_moderation_attempts",
            new_callable=AsyncMock,
            return_value=settings.MODERATION_MAX_ATTEMPTS + 1,
        ),
        patch("app.worker.main.reset_moderation_attempts", new_callable=AsyncMock) as mock_reset,
        patch("app.worker.main.add_history_step", new_callable=AsyncMock),
        patch("app.worker.main.handle_moderation_result", new_callable=AsyncMock) as mock_handle,
        patch("app.worker.main.valkey") as mock_valkey,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_valkey.hincrby = AsyncMock()
        mock_session_cls.return_value = _mock_session_cls_with(MagicMock())

        await analyze_trigger(task, msg)

    msg.nack.assert_not_called()
    msg.ack.assert_called_once()
    mock_handle.assert_called_once()
    assert mock_handle.call_args.args[2] is None  # result=None -> ветка AI Error
    assert mock_handle.call_args.kwargs["llm_used"] is False
    mock_reset.assert_called_once_with(task.trigger_id)


async def test_within_max_attempts_still_backs_off_and_nacks(msg):
    """Счётчик попыток ещё не превысил порог -- прежнее поведение: backoff + nack, без ack."""
    task = _make_task()

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch("app.worker.main.build_link_context", new_callable=AsyncMock, return_value=("", [])),
        patch("app.worker.main.moderate", new_callable=AsyncMock, side_effect=InferenceUnavailableError("boom")),
        patch("app.worker.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        patch(
            "app.worker.main.increment_moderation_attempts",
            new_callable=AsyncMock,
            return_value=1,
        ),
        patch("app.worker.main.reset_moderation_attempts", new_callable=AsyncMock) as mock_reset,
        patch("app.worker.main.add_history_step", new_callable=AsyncMock),
        patch("app.worker.main.handle_moderation_result", new_callable=AsyncMock) as mock_handle,
        patch("app.worker.main.valkey") as mock_valkey,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_valkey.hincrby = AsyncMock()
        mock_session_cls.return_value = _mock_session_cls_with(MagicMock())

        await analyze_trigger(task, msg)

    msg.ack.assert_not_called()
    msg.nack.assert_called_once()
    mock_handle.assert_not_called()
    mock_reset.assert_not_called()
    mock_sleep.assert_any_call(settings.MODERATION_FAIL_BACKOFF_SECONDS)


async def test_reset_moderation_attempts_called_on_success(msg):
    """Успешная обработка (moderate() вернул результат) -- счётчик попыток сбрасывается."""
    task = _make_task()
    mock_result = MagicMock(category="Safe", confidence=0.9, reasoning="ok")

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch("app.worker.main.build_link_context", new_callable=AsyncMock, return_value=("", [])),
        patch("app.worker.main.moderate", new_callable=AsyncMock, return_value=mock_result),
        patch("app.worker.main.reset_moderation_attempts", new_callable=AsyncMock) as mock_reset,
        patch("app.worker.main.add_history_step", new_callable=AsyncMock),
        patch("app.worker.main.handle_moderation_result", new_callable=AsyncMock),
        patch("app.worker.main.valkey") as mock_valkey,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_valkey.hincrby = AsyncMock()
        mock_session_cls.return_value = _mock_session_cls_with(MagicMock())

        await analyze_trigger(task, msg)

    mock_reset.assert_called_once_with(task.trigger_id)
    msg.ack.assert_called_once()


async def test_reset_moderation_attempts_called_when_moderate_returns_none(msg):
    """moderate() вернул None без исключения (например, формат-ошибка из части 1) -- счётчик тоже сбрасывается."""
    task = _make_task()

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch("app.worker.main.build_link_context", new_callable=AsyncMock, return_value=("", [])),
        patch("app.worker.main.moderate", new_callable=AsyncMock, return_value=None),
        patch("app.worker.main.reset_moderation_attempts", new_callable=AsyncMock) as mock_reset,
        patch("app.worker.main.add_history_step", new_callable=AsyncMock),
        patch("app.worker.main.handle_moderation_result", new_callable=AsyncMock) as mock_handle,
        patch("app.worker.main.valkey") as mock_valkey,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_valkey.hincrby = AsyncMock()
        mock_session_cls.return_value = _mock_session_cls_with(MagicMock())

        await analyze_trigger(task, msg)

    mock_reset.assert_called_once_with(task.trigger_id)
    mock_handle.assert_called_once()
    assert mock_handle.call_args.args[2] is None
    msg.ack.assert_called_once()


async def test_bulk_progress_incremented_when_max_attempts_exceeded_silent(msg):
    """silent=True + превышение лимита попыток -- bulk_remoderate_progress processed/flagged растут."""
    task = _make_task(silent=True)

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch("app.worker.main.build_link_context", new_callable=AsyncMock, return_value=("", [])),
        patch("app.worker.main.moderate", new_callable=AsyncMock, side_effect=InferenceUnavailableError("boom")),
        patch("app.worker.main.asyncio.sleep", new_callable=AsyncMock),
        patch(
            "app.worker.main.increment_moderation_attempts",
            new_callable=AsyncMock,
            return_value=settings.MODERATION_MAX_ATTEMPTS + 1,
        ),
        patch("app.worker.main.reset_moderation_attempts", new_callable=AsyncMock),
        patch("app.worker.main.add_history_step", new_callable=AsyncMock),
        patch("app.worker.main.handle_moderation_result", new_callable=AsyncMock),
        patch("app.worker.main.valkey") as mock_valkey,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_valkey.hincrby = AsyncMock()
        mock_session_cls.return_value = _mock_session_cls_with(MagicMock())

        await analyze_trigger(task, msg)

    mock_valkey.hincrby.assert_any_call("bulk_remoderate_progress", "processed", 1)
    mock_valkey.hincrby.assert_any_call("bulk_remoderate_progress", "flagged", 1)
    msg.ack.assert_called_once()
    msg.nack.assert_not_called()


async def test_max_attempts_exceeded_trigger_missing_acks_without_handle(msg):
    """Триггер уже отсутствует к моменту превышения лимита -- ack, handle_moderation_result не вызывается."""
    task = _make_task()

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch("app.worker.main.build_link_context", new_callable=AsyncMock, return_value=("", [])),
        patch("app.worker.main.moderate", new_callable=AsyncMock, side_effect=InferenceUnavailableError("boom")),
        patch("app.worker.main.asyncio.sleep", new_callable=AsyncMock),
        patch(
            "app.worker.main.increment_moderation_attempts",
            new_callable=AsyncMock,
            return_value=settings.MODERATION_MAX_ATTEMPTS + 1,
        ),
        patch("app.worker.main.reset_moderation_attempts", new_callable=AsyncMock),
        patch("app.worker.main.add_history_step", new_callable=AsyncMock),
        patch("app.worker.main.handle_moderation_result", new_callable=AsyncMock) as mock_handle,
        patch("app.worker.main.valkey") as mock_valkey,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_valkey.hincrby = AsyncMock()
        mock_session_cls.return_value = _mock_session_cls_with(None)

        await analyze_trigger(task, msg)

    mock_handle.assert_not_called()
    msg.ack.assert_called_once()
    msg.nack.assert_not_called()
