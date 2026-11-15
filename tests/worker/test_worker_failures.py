"""Неожиданный сбой в analyze_trigger не должен вешать очередь модерации."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.db.models.trigger import ModerationStatus
from app.schemas.moderation import TriggerModerationTask
from app.worker import service as worker_service
from app.worker.main import analyze_trigger
from tests.factories import create_chat, create_trigger


def _make_task(trigger_id: int = 4242) -> TriggerModerationTask:
    return TriggerModerationTask(
        trigger_id=trigger_id,
        chat_id=-100500,
        text_content=None,
        caption=None,
        file_id="file123",
        file_type="video",
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


async def test_media_failure_acks_and_flags_ai_error_after_max_attempts(msg):
    """Сбой обработки медиа после лимита попыток: FLAGGED + ack, а не вечная передоставка."""
    task = _make_task()

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch(
            "app.worker.main.process_media",
            new_callable=AsyncMock,
            side_effect=RuntimeError("collage exploded"),
        ),
        patch("app.worker.main.add_history_step", new_callable=AsyncMock),
        patch(
            "app.worker.main.increment_moderation_attempts",
            new_callable=AsyncMock,
            return_value=settings.MODERATION_MAX_ATTEMPTS + 1,
        ),
        patch("app.worker.main.reset_moderation_attempts", new_callable=AsyncMock),
        patch("app.worker.main.handle_moderation_result", new_callable=AsyncMock) as mock_handle,
        patch("app.worker.main.valkey") as mock_valkey,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_valkey.hincrby = AsyncMock()
        mock_session_cls.return_value = _mock_session_cls_with(MagicMock())

        await analyze_trigger(task, msg)

    mock_handle.assert_called_once()
    assert mock_handle.call_args.args[2] is None
    assert mock_handle.call_args.kwargs["llm_used"] is False
    msg.ack.assert_called_once()
    msg.nack.assert_not_called()


async def test_media_failure_below_limit_nacks_with_backoff(msg):
    """Сбой до лимита: короткий backoff и nack для повтора, без ack."""
    task = _make_task()

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch(
            "app.worker.main.process_media",
            new_callable=AsyncMock,
            side_effect=RuntimeError("download failed"),
        ),
        patch("app.worker.main.add_history_step", new_callable=AsyncMock),
        patch("app.worker.main.increment_moderation_attempts", new_callable=AsyncMock, return_value=1),
        patch("app.worker.main.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        patch("app.worker.main.handle_moderation_result", new_callable=AsyncMock) as mock_handle,
        patch("app.worker.main.valkey") as mock_valkey,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_valkey.hincrby = AsyncMock()
        mock_session_cls.return_value = _mock_session_cls_with(MagicMock())

        await analyze_trigger(task, msg)

    mock_handle.assert_not_called()
    msg.nack.assert_called_once()
    msg.ack.assert_not_called()
    mock_sleep.assert_awaited_once_with(settings.MODERATION_FAIL_BACKOFF_SECONDS)


async def test_media_failure_marks_trigger_flagged_and_alerts(db_session, msg):
    """Сквозная проверка: сбой медиа после лимита -> FLAGGED "AI Error", алерт, ack."""
    from app.worker import main as worker_main

    chat = await create_chat(db_session)
    trigger = await create_trigger(
        db_session,
        chat.id,
        moderation_status=ModerationStatus.PENDING,
    )
    await db_session.commit()
    task = _make_task(trigger_id=trigger.id)

    class _SessionCtx:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *_args):
            return False

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch(
            "app.worker.main.process_media",
            new_callable=AsyncMock,
            side_effect=RuntimeError("collage exploded"),
        ),
        patch(
            "app.worker.main.increment_moderation_attempts",
            new_callable=AsyncMock,
            return_value=settings.MODERATION_MAX_ATTEMPTS + 1,
        ),
        patch("app.worker.main.reset_moderation_attempts", new_callable=AsyncMock),
        patch("app.worker.service.register_moderation_outcome", new_callable=AsyncMock),
        patch.object(worker_main, "async_session", lambda: _SessionCtx()),
        patch("app.worker.main.valkey") as mock_valkey,
    ):
        mock_valkey.hincrby = AsyncMock()

        await analyze_trigger(task, msg)

    await db_session.refresh(trigger)
    assert trigger.moderation_status == ModerationStatus.FLAGGED
    assert trigger.moderation_reason == "AI Error"
    worker_service.broker.publish.assert_awaited()
    assert worker_service.broker.publish.call_args.args[0].category == "Error"
    msg.ack.assert_called_once()
    msg.nack.assert_not_called()
