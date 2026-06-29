"""Tests for analyze_trigger skip-guard — мок-уровень, без реального DB."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.schemas.moderation import TriggerModerationTask
from app.worker.main import analyze_trigger


def _make_task(trigger_id: int = 1, chat_id: int = -100500, silent: bool = False) -> TriggerModerationTask:
    return TriggerModerationTask(
        trigger_id=trigger_id,
        chat_id=chat_id,
        text_content="hello",
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


async def test_banned_chat_skips_inference(msg):
    """Если чат забанен — moderate() не вызывается, msg.ack() вызывается."""
    task = _make_task()

    # moderation_skip_reason вернёт "banned"
    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock) as mock_clear,
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value="banned"),
        patch("app.worker.main.moderate", new_callable=AsyncMock) as mock_moderate,
        patch("app.worker.main.add_history_step", new_callable=AsyncMock),
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        # Мок сессии: get() возвращает фиктивный триггер (не None), чтобы history step прошёл
        mock_trigger = MagicMock()
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_trigger)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        await analyze_trigger(task, msg)

    # Inference не вызван
    mock_moderate.assert_not_called()
    # Сообщение подтверждено
    msg.ack.assert_called_once()
    # processing status очищен
    mock_clear.assert_called_once()


async def test_inactive_chat_skips_inference(msg):
    """Если чат неактивен — moderate() не вызывается, msg.ack() вызывается."""
    task = _make_task()

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value="inactive"),
        patch("app.worker.main.moderate", new_callable=AsyncMock) as mock_moderate,
        patch("app.worker.main.add_history_step", new_callable=AsyncMock),
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_trigger = MagicMock()
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_trigger)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        await analyze_trigger(task, msg)

    mock_moderate.assert_not_called()
    msg.ack.assert_called_once()


async def test_deleted_trigger_no_history_step_when_missing(msg):
    """Для полностью отсутствующего триггера (session.get -> None) — history step не пишется."""
    task = _make_task()

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value="deleted"),
        patch("app.worker.main.moderate", new_callable=AsyncMock) as mock_moderate,
        patch("app.worker.main.add_history_step", new_callable=AsyncMock) as mock_history,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        # session.get возвращает None — триггер полностью отсутствует
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=None)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        await analyze_trigger(task, msg)

    mock_moderate.assert_not_called()
    msg.ack.assert_called_once()
    # Не должно быть вызова add_history_step (FK бы упал)
    mock_history.assert_not_called()


async def test_silent_skip_increments_bulk_progress(msg):
    """При silent=True и skip — hincrby processed +1 вызывается до ack."""
    task = _make_task(silent=True)

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value="banned"),
        patch("app.worker.main.moderate", new_callable=AsyncMock) as mock_moderate,
        patch("app.worker.main.add_history_step", new_callable=AsyncMock),
        patch("app.worker.main.valkey") as mock_valkey,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_valkey.hincrby = AsyncMock()
        mock_trigger = MagicMock()
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_trigger)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        await analyze_trigger(task, msg)

    mock_moderate.assert_not_called()
    mock_valkey.hincrby.assert_called_once_with("bulk_remoderate_progress", "processed", 1)
    msg.ack.assert_called_once()


async def test_non_silent_skip_does_not_increment_bulk_progress(msg):
    """При silent=False и skip — hincrby не вызывается."""
    task = _make_task(silent=False)

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value="banned"),
        patch("app.worker.main.moderate", new_callable=AsyncMock),
        patch("app.worker.main.add_history_step", new_callable=AsyncMock),
        patch("app.worker.main.valkey") as mock_valkey,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_valkey.hincrby = AsyncMock()
        mock_trigger = MagicMock()
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=mock_trigger)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        await analyze_trigger(task, msg)

    mock_valkey.hincrby.assert_not_called()
    msg.ack.assert_called_once()


async def test_no_skip_reason_proceeds_normally(msg):
    """Если skip_reason=None — анализ идёт штатно (moderate вызывается)."""
    task = _make_task()

    mock_result = MagicMock()
    mock_result.category = "Safe"
    mock_result.confidence = 0.9
    mock_result.reasoning = "ok"

    with (
        patch("app.worker.main.set_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.clear_processing_status", new_callable=AsyncMock),
        patch("app.worker.main.moderation_skip_reason", new_callable=AsyncMock, return_value=None),
        patch("app.worker.main.moderate", new_callable=AsyncMock, return_value=mock_result) as mock_moderate,
        patch("app.worker.main.add_history_step", new_callable=AsyncMock),
        patch("app.worker.main.handle_moderation_result", new_callable=AsyncMock),
        patch("app.worker.main.valkey") as mock_valkey,
        patch("app.worker.main.async_session") as mock_session_cls,
    ):
        mock_valkey.hincrby = AsyncMock()
        mock_session = AsyncMock()
        mock_session.get = AsyncMock(return_value=MagicMock())
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = mock_session

        await analyze_trigger(task, msg)

    # moderate должен быть вызван
    mock_moderate.assert_called_once()
    msg.ack.assert_called_once()
