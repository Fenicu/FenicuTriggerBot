"""Integration: moderation_skip_reason для протухших чатов."""

import pytest

from app.db.models.trigger import ModerationStatus
from app.worker.service import moderation_skip_reason
from tests.factories import create_banned_chat, create_chat, create_trigger


@pytest.mark.asyncio
async def test_valid_trigger_returns_none(db_session):
    """Активный чат, живой триггер — пропускать не нужно."""
    chat = await create_chat(db_session)
    t = await create_trigger(db_session, chat_id=chat.id, moderation_status=ModerationStatus.PENDING)
    await db_session.commit()
    assert await moderation_skip_reason(db_session, t.id) is None


@pytest.mark.asyncio
async def test_deleted_trigger_returns_deleted(db_session):
    """Soft-deleted триггер — возвращает 'deleted'."""
    chat = await create_chat(db_session)
    t = await create_trigger(db_session, chat_id=chat.id, is_deleted=True)
    await db_session.commit()
    assert await moderation_skip_reason(db_session, t.id) == "deleted"


@pytest.mark.asyncio
async def test_missing_trigger_returns_deleted(db_session):
    """Несуществующий триггер — возвращает 'deleted'."""
    assert await moderation_skip_reason(db_session, 999999) == "deleted"


@pytest.mark.asyncio
async def test_banned_chat_returns_banned(db_session):
    """Забаненный чат — возвращает 'banned'."""
    chat = await create_chat(db_session)
    t = await create_trigger(db_session, chat_id=chat.id)
    await create_banned_chat(db_session, chat_id=chat.id)
    await db_session.commit()
    assert await moderation_skip_reason(db_session, t.id) == "banned"


@pytest.mark.asyncio
async def test_inactive_chat_returns_inactive(db_session):
    """Неактивный чат (бот вышел) — возвращает 'inactive'."""
    chat = await create_chat(db_session, is_active=False)
    t = await create_trigger(db_session, chat_id=chat.id)
    await db_session.commit()
    assert await moderation_skip_reason(db_session, t.id) == "inactive"
