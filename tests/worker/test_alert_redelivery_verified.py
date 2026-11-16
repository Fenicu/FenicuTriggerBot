"""Повторная доставка: потерянный алерт модерации отправляется заново."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.db.models.moderation_history import ModerationHistory, ModerationStep
from app.db.models.trigger import ModerationStatus
from app.schemas.moderation import TriggerModerationTask
from app.worker.main import _finish_skipped
from tests.factories import create_chat, create_trigger


@pytest.fixture
def msg():
    message = AsyncMock()
    message.ack = AsyncMock()
    return message


@pytest.fixture
def broker_mock():
    from app.worker.service import broker

    broker.publish.reset_mock()
    return broker


@pytest.fixture(autouse=True)
def _mock_main_valkey(monkeypatch):
    monkeypatch.setattr("app.worker.main.valkey", AsyncMock())


async def _flagged_trigger(session, **overrides):
    chat = await create_chat(session)
    defaults = {
        "moderation_status": ModerationStatus.FLAGGED,
        "moderation_reason": "Scam: casino links",
        "moderation_category": "Scam",
        "moderation_confidence": 0.91,
    }
    defaults.update(overrides)
    trigger = await create_trigger(session, chat_id=chat.id, **defaults)
    await session.commit()
    return trigger


async def _add_step(session, trigger_id: int, step: ModerationStep, details: dict | None = None) -> None:
    session.add(ModerationHistory(trigger_id=trigger_id, step=step.value, details=details))
    await session.commit()


def _task(trigger, *, silent: bool = False) -> TriggerModerationTask:
    return TriggerModerationTask(
        trigger_id=trigger.id,
        chat_id=trigger.chat_id,
        text_content="spam",
        silent=silent,
    )


async def _history_steps(session, trigger_id: int) -> list[str]:
    stmt = (
        select(ModerationHistory)
        .where(ModerationHistory.trigger_id == trigger_id)
        .order_by(ModerationHistory.created_at, ModerationHistory.id)
    )
    return [row.step for row in (await session.execute(stmt)).scalars().all()]


async def test_redelivery_republishes_missing_alert(db_session, msg, broker_mock):
    """FLAGGED без ALERT_SENT после вердикта — алерт публикуется и отмечается в истории."""
    trigger = await _flagged_trigger(db_session)
    await _add_step(
        db_session,
        trigger.id,
        ModerationStep.AUTO_FLAGGED,
        details={"category": "Scam", "confidence": 0.91, "reasoning": "casino links"},
    )

    await _finish_skipped(db_session, _task(trigger), msg, "already_moderated")

    broker_mock.publish.assert_awaited_once()
    alert = broker_mock.publish.call_args.args[0]
    assert alert.trigger_id == trigger.id
    assert alert.category == "Scam"
    assert alert.confidence == 0.91
    assert alert.reasoning == "casino links"
    assert await _history_steps(db_session, trigger.id) == [
        ModerationStep.AUTO_FLAGGED.value,
        ModerationStep.SKIPPED.value,
        ModerationStep.ALERT_SENT.value,
    ]
    msg.ack.assert_awaited_once()


async def test_redelivery_does_not_duplicate_sent_alert(db_session, msg, broker_mock):
    """ALERT_SENT после последнего вердикта — повторно не публикуем."""
    trigger = await _flagged_trigger(db_session)
    await _add_step(db_session, trigger.id, ModerationStep.AUTO_FLAGGED, details={"category": "Scam"})
    await _add_step(db_session, trigger.id, ModerationStep.ALERT_SENT)

    await _finish_skipped(db_session, _task(trigger), msg, "already_moderated")

    broker_mock.publish.assert_not_awaited()
    msg.ack.assert_awaited_once()


async def test_redelivery_of_new_verdict_after_old_alert_republishes(db_session, msg, broker_mock):
    """ALERT_SENT относится к старому вердикту — после нового вердикта алерт нужен снова."""
    trigger = await _flagged_trigger(db_session)
    await _add_step(db_session, trigger.id, ModerationStep.AUTO_FLAGGED, details={"category": "Scam"})
    await _add_step(db_session, trigger.id, ModerationStep.ALERT_SENT)
    await _add_step(
        db_session,
        trigger.id,
        ModerationStep.AUTO_FLAGGED,
        details={"category": "Porn", "confidence": 0.8, "reasoning": "explicit"},
    )

    await _finish_skipped(db_session, _task(trigger), msg, "already_moderated")

    alert = broker_mock.publish.call_args.args[0]
    assert alert.category == "Porn"


async def test_redelivery_silent_task_does_not_publish(db_session, msg, broker_mock):
    """Silent-перемодерация не шлёт алерты."""
    trigger = await _flagged_trigger(db_session)
    await _add_step(
        db_session,
        trigger.id,
        ModerationStep.AUTO_FLAGGED,
        details={"category": "Scam", "reasoning": "casino links"},
    )

    await _finish_skipped(db_session, _task(trigger, silent=True), msg, "already_moderated")

    broker_mock.publish.assert_not_awaited()


async def test_redelivery_of_manually_decided_trigger_does_not_publish(db_session, msg, broker_mock):
    """Триггер уже решён модератором (статус не FLAGGED) — алерт не нужен."""
    trigger = await _flagged_trigger(db_session, moderation_status=ModerationStatus.SAFE)
    await _add_step(
        db_session,
        trigger.id,
        ModerationStep.AUTO_FLAGGED,
        details={"category": "Scam", "reasoning": "casino links"},
    )

    await _finish_skipped(db_session, _task(trigger), msg, "already_moderated")

    broker_mock.publish.assert_not_awaited()


async def test_redelivery_republishes_ai_error_alert(db_session, msg, broker_mock):
    """Вердикт AI Error восстанавливает поля алерта категории Error."""
    trigger = await _flagged_trigger(
        db_session,
        moderation_reason="AI Error",
        moderation_category=None,
        moderation_confidence=None,
    )
    await _add_step(
        db_session,
        trigger.id,
        ModerationStep.AUTO_ERROR,
        details={"error": "AI failed to process"},
    )

    await _finish_skipped(db_session, _task(trigger), msg, "already_moderated")

    alert = broker_mock.publish.call_args.args[0]
    assert alert.category == "Error"
    assert alert.reasoning == "AI failed to process"
