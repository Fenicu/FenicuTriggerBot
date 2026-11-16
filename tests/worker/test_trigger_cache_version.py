"""Воркер модерации сбрасывает кэш триггеров чата с версией, а не простым DEL."""

from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.trigger import ModerationStatus
from app.schemas.moderation import ModerationLLMResult
from app.services import trigger_service
from tests.factories import create_chat, create_trigger, create_user

RESULTS = {
    "safe": ModerationLLMResult(category="Safe", confidence=0.99, reasoning="Clean"),
    "flagged": ModerationLLMResult(category="Scam", confidence=0.99, reasoning="Bad"),
    "error": None,
}


@pytest.fixture(autouse=True)
def _real_valkey(valkey_client):
    with (
        patch("app.worker.service.valkey", valkey_client),
        patch("app.services.trigger_service.valkey", valkey_client),
    ):
        yield valkey_client


@pytest.fixture
async def pending_trigger(db_session: AsyncSession):
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    trigger = await create_trigger(
        db_session, chat_id=chat.id, user_id=user.id, moderation_status=ModerationStatus.PENDING
    )
    await db_session.commit()
    return trigger


@pytest.mark.parametrize("outcome", sorted(RESULTS))
async def test_moderation_result_bumps_cache_version(db_session, pending_trigger, _real_valkey, outcome):
    from app.worker.service import handle_moderation_result

    chat_id = pending_trigger.chat_id
    await trigger_service.get_triggers_by_chat(db_session, chat_id)
    assert await _real_valkey.exists(f"triggers:{chat_id}") == 1

    await handle_moderation_result(db_session, pending_trigger, RESULTS[outcome], silent=True)

    assert await _real_valkey.get(f"triggers_ver:{chat_id}") == "1"
    assert await _real_valkey.exists(f"triggers:{chat_id}") == 0


async def test_reader_racing_with_moderation_does_not_keep_old_status(db_session, pending_trigger, _real_valkey):
    """Список, прочитанный до вердикта и записанный в кэш после него, больше не принимается."""
    from app.worker.service import handle_moderation_result

    chat_id = pending_trigger.chat_id
    stale = await trigger_service.get_triggers_by_chat(db_session, chat_id)
    stale_payload = await _real_valkey.get(f"triggers:{chat_id}")
    assert stale[0].moderation_status is ModerationStatus.PENDING

    await handle_moderation_result(db_session, pending_trigger, RESULTS["safe"], silent=True)
    # Опоздавший читатель кладёт старый список обратно
    await _real_valkey.set(f"triggers:{chat_id}", stale_payload)

    fresh = await trigger_service.get_triggers_by_chat(db_session, chat_id)
    assert fresh[0].moderation_status is ModerationStatus.SAFE
