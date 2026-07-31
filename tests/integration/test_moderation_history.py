"""Integration tests for app/services/moderation_history_service.py."""

import json

from app.core.valkey import valkey
from app.db.models.moderation_history import ModerationHistory, ModerationStep
from app.services.moderation_history_service import (
    SSE_CHANNEL_PREFIX,
    add_history_step,
    get_current_step,
    get_history_by_trigger,
)
from tests.factories import create_chat, create_trigger, create_user


# ── add_history_step ─────────────────────────────────────────────────────────


async def test_add_history_step_creates_record(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id)
    await db_session.commit()

    history = await add_history_step(db_session, trigger.id, ModerationStep.CREATED)
    await db_session.commit()

    assert history.id is not None
    assert history.trigger_id == trigger.id
    assert history.step == ModerationStep.CREATED.value
    assert history.details is None
    assert history.actor_id is None


async def test_add_history_step_with_details(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id)
    await db_session.commit()

    details = {"reason": "manual check", "score": 0.85}
    history = await add_history_step(db_session, trigger.id, ModerationStep.AI_COMPLETED, details=details)
    await db_session.commit()

    assert history.details == details


async def test_add_history_step_with_actor(db_session):
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id, user_id=user.id)
    await db_session.commit()

    history = await add_history_step(
        db_session,
        trigger.id,
        ModerationStep.MANUAL_APPROVED,
        details={"admin_id": user.id},
        actor_id=user.id,
    )
    await db_session.commit()

    assert history.actor_id == user.id


async def test_add_history_step_publishes_to_valkey(db_session, _mock_valkey_for_services):
    mock_valkey = _mock_valkey_for_services
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id)
    await db_session.commit()

    await add_history_step(db_session, trigger.id, ModerationStep.QUEUED)
    await db_session.commit()

    mock_valkey.publish.assert_called()
    channel = mock_valkey.publish.call_args[0][0]
    assert channel == f"{SSE_CHANNEL_PREFIX}{trigger.id}"

    payload = json.loads(mock_valkey.publish.call_args[0][1])
    assert payload["trigger_id"] == trigger.id
    assert payload["step"] == ModerationStep.QUEUED.value


async def test_add_history_step_publish_payload_format(db_session):
    chat = await create_chat(db_session)
    actor = await create_user(db_session, first_name="Actor")
    trigger = await create_trigger(db_session, chat_id=chat.id)
    await db_session.commit()

    details = {"category": "Safe"}
    await add_history_step(db_session, trigger.id, ModerationStep.AUTO_APPROVED, details=details, actor_id=actor.id)
    await db_session.commit()

    from app.services.moderation_history_service import valkey as svc_valkey

    payload = json.loads(svc_valkey.publish.call_args[0][1])
    assert payload["id"] is not None
    assert payload["trigger_id"] == trigger.id
    assert payload["step"] == ModerationStep.AUTO_APPROVED.value
    assert payload["details"] == details
    assert payload["actor_id"] == actor.id
    assert "created_at" in payload


async def test_add_history_step_multiple_steps(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id)
    await db_session.commit()

    await add_history_step(db_session, trigger.id, ModerationStep.CREATED)
    await add_history_step(db_session, trigger.id, ModerationStep.QUEUED)
    await add_history_step(db_session, trigger.id, ModerationStep.PROCESSING_STARTED)
    await db_session.commit()

    history = await get_history_by_trigger(db_session, trigger.id)
    assert len(history) == 3


# ── get_history_by_trigger ───────────────────────────────────────────────────


async def test_get_history_by_trigger_returns_ordered(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id)
    await db_session.commit()

    await add_history_step(db_session, trigger.id, ModerationStep.CREATED)
    await add_history_step(db_session, trigger.id, ModerationStep.QUEUED)
    await add_history_step(db_session, trigger.id, ModerationStep.AI_ANALYZING)
    await add_history_step(db_session, trigger.id, ModerationStep.AUTO_APPROVED)
    await db_session.commit()

    history = await get_history_by_trigger(db_session, trigger.id)
    assert len(history) == 4
    assert history[0].step == ModerationStep.CREATED.value
    assert history[1].step == ModerationStep.QUEUED.value
    assert history[2].step == ModerationStep.AI_ANALYZING.value
    assert history[3].step == ModerationStep.AUTO_APPROVED.value

    # Verify ordering by created_at (ascending)
    for i in range(len(history) - 1):
        assert history[i].created_at <= history[i + 1].created_at


async def test_get_history_by_trigger_nonexistent_trigger(db_session):
    history = await get_history_by_trigger(db_session, 999999)
    assert history == []


async def test_get_history_by_trigger_isolates_triggers(db_session):
    chat = await create_chat(db_session)
    trigger1 = await create_trigger(db_session, chat_id=chat.id, key_phrase="iso1")
    trigger2 = await create_trigger(db_session, chat_id=chat.id, key_phrase="iso2")
    await db_session.commit()

    await add_history_step(db_session, trigger1.id, ModerationStep.CREATED)
    await add_history_step(db_session, trigger1.id, ModerationStep.QUEUED)
    await add_history_step(db_session, trigger2.id, ModerationStep.CREATED)
    await db_session.commit()

    history1 = await get_history_by_trigger(db_session, trigger1.id)
    history2 = await get_history_by_trigger(db_session, trigger2.id)

    assert len(history1) == 2
    assert len(history2) == 1


# ── get_current_step ─────────────────────────────────────────────────────────


async def test_get_current_step_empty_history():
    result = get_current_step([])
    assert result == ModerationStep.CREATED.value


async def test_get_current_step_returns_last(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id)
    await db_session.commit()

    await add_history_step(db_session, trigger.id, ModerationStep.CREATED)
    await add_history_step(db_session, trigger.id, ModerationStep.QUEUED)
    await add_history_step(db_session, trigger.id, ModerationStep.AUTO_FLAGGED)
    await db_session.commit()

    history = await get_history_by_trigger(db_session, trigger.id)
    current = get_current_step(history)
    assert current == ModerationStep.AUTO_FLAGGED.value


async def test_get_current_step_single_entry(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id)
    await db_session.commit()

    await add_history_step(db_session, trigger.id, ModerationStep.CREATED)
    await db_session.commit()

    history = await get_history_by_trigger(db_session, trigger.id)
    current = get_current_step(history)
    assert current == ModerationStep.CREATED.value


async def test_get_current_step_after_requeue(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id)
    await db_session.commit()

    await add_history_step(db_session, trigger.id, ModerationStep.CREATED)
    await add_history_step(db_session, trigger.id, ModerationStep.QUEUED)
    await add_history_step(db_session, trigger.id, ModerationStep.AUTO_FLAGGED)
    await add_history_step(db_session, trigger.id, ModerationStep.REQUEUED)
    await db_session.commit()

    history = await get_history_by_trigger(db_session, trigger.id)
    current = get_current_step(history)
    assert current == ModerationStep.REQUEUED.value


async def test_get_history_by_trigger_preserves_insertion_order_on_tied_timestamps(db_session):
    """Шаги, вставленные в одной транзакции (одинаковый func.now()), должны идти в порядке вставки."""
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id)
    await db_session.commit()

    steps = [
        ModerationStep.CREATED,
        ModerationStep.QUEUED,
        ModerationStep.PROCESSING_STARTED,
        ModerationStep.AI_ANALYZING,
    ]
    inserted = [await add_history_step(db_session, trigger.id, step) for step in steps]
    await db_session.commit()

    # Убедимся, что таймстемпы действительно совпали (одна транзакция -> один func.now()) --
    # иначе тест не воспроизводит баг с неопределённым порядком
    assert len({h.created_at for h in inserted}) == 1

    history = await get_history_by_trigger(db_session, trigger.id)
    assert [h.step for h in history] == [s.value for s in steps]


async def test_add_history_step_created_at_is_set(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id)
    await db_session.commit()

    history = await add_history_step(db_session, trigger.id, ModerationStep.CREATED)
    await db_session.commit()

    assert history.created_at is not None
