"""Регрессия tag_service: уровень сохраняется только после успешного вызова API."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user_chat import UserChat
from app.services.reputation_service import add_message_score
from app.services.tag_service import update_tag_if_needed
from tests.factories import create_chat, create_user


async def _make_user_chat(db_session: AsyncSession, user_id: int, chat_id: int, **overrides) -> UserChat:
    defaults = {
        "user_id": user_id,
        "chat_id": chat_id,
        "is_active": True,
        "reputation_score": 0,
        "reputation_level": 0,
        "tag": None,
        "tag_is_manual": False,
    }
    defaults.update(overrides)
    uc = UserChat(**defaults)
    db_session.add(uc)
    await db_session.flush()
    return uc


@pytest.fixture
async def chat(db_session: AsyncSession):
    return await create_chat(db_session, tags_enabled=True, tags_preset="neutral", language_code="ru")


@pytest.fixture
async def user(db_session: AsyncSession):
    return await create_user(db_session)


async def test_level_kept_when_tag_call_fails(db_session, chat, user):
    """Неудачный вызов API не должен фиксировать новый уровень — иначе тег не переедет."""
    uc = await _make_user_chat(db_session, user.id, chat.id, reputation_level=0, reputation_score=100)

    with patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock, return_value=False):
        await update_tag_if_needed(AsyncMock(), db_session, uc, chat, 1)

    assert uc.reputation_level == 0
    assert uc.tag is None


async def test_level_persisted_when_tag_call_succeeds(db_session, chat, user):
    uc = await _make_user_chat(db_session, user.id, chat.id, reputation_level=0, reputation_score=100)

    with patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock, return_value=True):
        await update_tag_if_needed(AsyncMock(), db_session, uc, chat, 1)

    assert uc.reputation_level == 1
    assert uc.tag == "Участник"


async def test_manual_tag_still_advances_level(db_session, chat, user):
    """Ручной тег не трогаем, но уровень репутации обязан расти."""
    uc = await _make_user_chat(db_session, user.id, chat.id, tag="VIP", tag_is_manual=True)

    with patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock) as mock_set:
        await update_tag_if_needed(AsyncMock(), db_session, uc, chat, 2)

    mock_set.assert_not_called()
    assert uc.reputation_level == 2
    assert uc.tag == "VIP"


async def test_failed_tag_call_is_retried_on_next_message(db_session, chat, user):
    """После неудачи следующее сообщение должно снова пытаться поставить тег."""
    uc = await _make_user_chat(db_session, user.id, chat.id, reputation_level=0, reputation_score=49)

    first_level = await add_message_score(db_session, uc, chat)
    assert first_level == 1

    with patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock, return_value=False):
        await update_tag_if_needed(AsyncMock(), db_session, uc, chat, first_level)

    assert uc.reputation_level == 0

    second_level = await add_message_score(db_session, uc, chat)
    assert second_level == 1, "уровень не зафиксирован, попытка должна повториться"

    with patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock, return_value=True):
        await update_tag_if_needed(AsyncMock(), db_session, uc, chat, second_level)

    assert uc.reputation_level == 1
    assert uc.tag == "Участник"
