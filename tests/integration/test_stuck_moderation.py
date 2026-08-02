"""Integration: страховочный подбор зависших PENDING-триггеров (app/services/stuck_moderation.py)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.core.config import settings
from app.db.models.trigger import ModerationStatus
from app.services import stuck_moderation
from app.services.stuck_moderation import requeue_stuck_triggers
from tests.factories import create_banned_chat, create_chat, create_trigger

OLD_ENOUGH = timedelta(minutes=settings.MODERATION_STUCK_AFTER_MINUTES + 10)
TOO_YOUNG = timedelta(minutes=settings.MODERATION_STUCK_AFTER_MINUTES - 10)


def _stuck_created_at() -> datetime:
    """created_at заведомо старше порога MODERATION_STUCK_AFTER_MINUTES."""
    return datetime.now(timezone.utc) - OLD_ENOUGH


async def test_stuck_pending_without_marker_is_requeued(db_session, _mock_broker_for_services):
    """PENDING-триггер старше порога без processing-маркера -- переотправляется."""
    chat = await create_chat(db_session)
    trigger = await create_trigger(
        db_session,
        chat_id=chat.id,
        moderation_status=ModerationStatus.PENDING,
        created_at=_stuck_created_at(),
    )
    await db_session.commit()

    count = await requeue_stuck_triggers()

    assert count == 1
    _mock_broker_for_services.publish.assert_awaited()
    await db_session.refresh(trigger)
    assert trigger.moderation_status == ModerationStatus.PENDING


async def test_pending_with_active_processing_marker_not_requeued(db_session, _mock_valkey_for_services):
    """PENDING-триггер старше порога, но с активным processing-маркером -- не трогается."""
    chat = await create_chat(db_session)
    trigger = await create_trigger(
        db_session,
        chat_id=chat.id,
        moderation_status=ModerationStatus.PENDING,
        created_at=_stuck_created_at(),
    )
    await db_session.commit()

    marker_key = f"trigger_processing:{trigger.id}"
    _mock_valkey_for_services.exists.side_effect = lambda key: 1 if key == marker_key else 0

    count = await requeue_stuck_triggers()

    assert count == 0


async def test_pending_younger_than_threshold_not_requeued(db_session):
    """PENDING-триггер моложе порога -- ещё не считается зависшим."""
    chat = await create_chat(db_session)
    await create_trigger(
        db_session,
        chat_id=chat.id,
        moderation_status=ModerationStatus.PENDING,
        created_at=datetime.now(timezone.utc) - TOO_YOUNG,
    )
    await db_session.commit()

    count = await requeue_stuck_triggers()

    assert count == 0


async def test_safe_trigger_not_requeued(db_session):
    """Триггер в статусе SAFE не подбирается, даже если он старый."""
    chat = await create_chat(db_session)
    await create_trigger(
        db_session,
        chat_id=chat.id,
        moderation_status=ModerationStatus.SAFE,
        created_at=_stuck_created_at(),
    )
    await db_session.commit()

    count = await requeue_stuck_triggers()

    assert count == 0


async def test_flagged_trigger_not_requeued(db_session):
    """Триггер в статусе FLAGGED не подбирается."""
    chat = await create_chat(db_session)
    await create_trigger(
        db_session,
        chat_id=chat.id,
        moderation_status=ModerationStatus.FLAGGED,
        created_at=_stuck_created_at(),
    )
    await db_session.commit()

    count = await requeue_stuck_triggers()

    assert count == 0


async def test_soft_deleted_pending_not_requeued(db_session):
    """Мягко удалённый PENDING-триггер не подбирается."""
    chat = await create_chat(db_session)
    await create_trigger(
        db_session,
        chat_id=chat.id,
        moderation_status=ModerationStatus.PENDING,
        created_at=_stuck_created_at(),
        is_deleted=True,
        deleted_at=datetime.now(timezone.utc),
    )
    await db_session.commit()

    count = await requeue_stuck_triggers()

    assert count == 0


async def test_pending_in_banned_chat_not_requeued(db_session):
    """PENDING-триггер из забаненного чата не подбирается."""
    chat = await create_chat(db_session)
    await create_trigger(
        db_session,
        chat_id=chat.id,
        moderation_status=ModerationStatus.PENDING,
        created_at=_stuck_created_at(),
    )
    await create_banned_chat(db_session, chat_id=chat.id)
    await db_session.commit()

    count = await requeue_stuck_triggers()

    assert count == 0


async def test_pending_in_inactive_chat_not_requeued(db_session):
    """PENDING-триггер неактивного чата (бот вышел) не подбирается."""
    chat = await create_chat(db_session, is_active=False)
    await create_trigger(
        db_session,
        chat_id=chat.id,
        moderation_status=ModerationStatus.PENDING,
        created_at=_stuck_created_at(),
    )
    await db_session.commit()

    count = await requeue_stuck_triggers()

    assert count == 0


async def test_batch_limited_to_configured_size(db_session, monkeypatch):
    """Пачка ограничена лимитом -- лишние кандидаты остаются на следующий прогон."""
    monkeypatch.setattr(stuck_moderation, "STUCK_TRIGGERS_BATCH_LIMIT", 3)

    chat = await create_chat(db_session)
    for i in range(5):
        await create_trigger(
            db_session,
            chat_id=chat.id,
            key_phrase=f"stuck_{i}",
            moderation_status=ModerationStatus.PENDING,
            created_at=_stuck_created_at(),
        )
    await db_session.commit()

    count = await requeue_stuck_triggers()

    assert count == 3


async def test_requeue_failure_for_one_trigger_does_not_abort_others(db_session):
    """Сбой requeue_trigger по одному кандидату не должен срывать обработку остальных."""
    chat = await create_chat(db_session)
    bad = await create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="bad",
        moderation_status=ModerationStatus.PENDING,
        created_at=_stuck_created_at(),
    )
    good = await create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="good",
        moderation_status=ModerationStatus.PENDING,
        created_at=_stuck_created_at(),
    )
    await db_session.commit()

    real_requeue_trigger = stuck_moderation.requeue_trigger

    async def flaky_requeue_trigger(session, trigger_id):
        if trigger_id == bad.id:
            raise RuntimeError("boom")
        return await real_requeue_trigger(session, trigger_id)

    with patch("app.services.stuck_moderation.requeue_trigger", side_effect=flaky_requeue_trigger):
        count = await requeue_stuck_triggers()

    assert count == 1

    await db_session.refresh(good)
    assert good.moderation_status == ModerationStatus.PENDING
