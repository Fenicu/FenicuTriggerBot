"""Тесты регистрации задач планировщика в app.worker.main.start_scheduler."""

from unittest.mock import MagicMock, patch

from app.services.stuck_moderation import requeue_stuck_triggers
from app.worker.main import start_scheduler


async def test_start_scheduler_registers_stuck_moderation_sweep():
    """requeue_stuck_triggers должен ставиться на интервал 10 минут."""
    with patch("app.worker.main.scheduler") as mock_scheduler:
        await start_scheduler()

    matching_calls = [
        call for call in mock_scheduler.add_job.call_args_list if call.args and call.args[0] is requeue_stuck_triggers
    ]
    assert len(matching_calls) == 1

    call = matching_calls[0]
    assert call.args[1] == "interval"
    assert call.kwargs.get("minutes") == 10
