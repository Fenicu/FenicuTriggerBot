"""Тесты регистрации задач планировщика в app.worker.main.start_scheduler."""

from unittest.mock import patch

from app.core.tasks import update_gban_task
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


async def test_start_scheduler_registers_gban_when_enabled():
    with (
        patch("app.worker.main.settings") as mock_settings,
        patch("app.worker.main.scheduler") as mock_scheduler,
    ):
        mock_settings.GBAN_UPDATE_ENABLED = True

        await start_scheduler()

    gban_calls = [call for call in mock_scheduler.add_job.call_args_list if call.args and call.args[0] is update_gban_task]
    assert len(gban_calls) == 2


async def test_start_scheduler_skips_gban_when_disabled():
    with (
        patch("app.worker.main.settings") as mock_settings,
        patch("app.worker.main.scheduler") as mock_scheduler,
    ):
        mock_settings.GBAN_UPDATE_ENABLED = False

        await start_scheduler()

    gban_calls = [call for call in mock_scheduler.add_job.call_args_list if call.args and call.args[0] is update_gban_task]
    assert gban_calls == []
