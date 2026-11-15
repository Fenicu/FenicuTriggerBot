from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.chat import BannedChat, Chat
from app.db.models.trigger import ModerationStatus, Trigger
from app.schemas.moderation import ModerationLLMResult, TriggerModerationTask
from app.worker import main as worker
from tests.factories import create_chat, create_trigger


@pytest.mark.parametrize("phase", ["before_inference", "before_result"])
@pytest.mark.parametrize("change", ["soft_delete", "hard_delete", "safe", "banned", "inactive_chat", "banned_chat"])
async def test_worker_observes_external_changes_before_expensive_or_final_work(db_session, phase, change):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat.id, moderation_status=ModerationStatus.PENDING)
    await db_session.commit()
    task = TriggerModerationTask(
        trigger_id=trigger.id, chat_id=chat.id, text_content="check this", link_urls=["https://hidden.example"]
    )
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def mutate():
        async with factory() as writer:
            if change == "hard_delete":
                await writer.execute(delete(Trigger).where(Trigger.id == trigger.id))
            elif change == "soft_delete":
                await writer.execute(update(Trigger).where(Trigger.id == trigger.id).values(is_deleted=True))
            elif change in ("safe", "banned"):
                await writer.execute(
                    update(Trigger).where(Trigger.id == trigger.id).values(moderation_status=ModerationStatus(change))
                )
            elif change == "inactive_chat":
                await writer.execute(update(Chat).where(Chat.id == chat.id).values(is_active=False))
            else:
                writer.add(BannedChat(chat_id=chat.id, reason="test"))
            await writer.commit()

    async def build_links(*args):
        assert args[2] == ["https://hidden.example"]
        if phase == "before_inference":
            await mutate()
        return "", []

    async def infer(**kwargs):
        if phase == "before_result":
            await mutate()
        return ModerationLLMResult(category="Scam", confidence=0.99, reasoning="test")

    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=db_session)
    session_context.__aexit__ = AsyncMock(return_value=False)
    msg = AsyncMock()
    with (
        patch.object(worker, "async_session", return_value=session_context),
        patch.object(worker, "set_processing_status", AsyncMock()),
        patch.object(worker, "clear_processing_status", AsyncMock()),
        patch.object(worker, "reset_moderation_attempts", AsyncMock()),
        patch.object(worker, "add_history_step", AsyncMock()),
        patch.object(worker, "build_link_context", side_effect=build_links),
        patch.object(worker, "moderate", side_effect=infer) as moderate,
        patch.object(worker, "handle_moderation_result", AsyncMock()) as handle,
        patch.object(worker, "valkey", AsyncMock()),
    ):
        await worker._analyze_trigger(task, msg)
    handle.assert_not_awaited()
    assert moderate.await_count == (0 if phase == "before_inference" else 1)
    msg.ack.assert_awaited_once()
    msg.nack.assert_not_awaited()
