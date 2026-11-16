"""Без права на теги уровень всё равно фиксируется, чтобы /status не отставал."""

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
        "reputation_score": 100,
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


async def test_level_persisted_when_tag_permission_cached(db_session, chat, user):
    """Права на теги нет (кэш) — уровень фиксируем, тег не трогаем."""
    uc = await _make_user_chat(db_session, user.id, chat.id)

    with (
        patch("app.services.tag_service.tag_calls_blocked", new_callable=AsyncMock, return_value=True),
        patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock) as mock_set,
    ):
        await update_tag_if_needed(AsyncMock(), db_session, uc, chat, 1)

    mock_set.assert_not_called()
    assert uc.reputation_level == 1
    assert uc.tag is None


async def test_level_persisted_when_failure_reveals_missing_permission(db_session, chat, user):
    """Ошибка сама закэшировала отсутствие права — это не временный сбой."""
    uc = await _make_user_chat(db_session, user.id, chat.id)

    with (
        patch(
            "app.services.tag_service.tag_calls_blocked",
            new_callable=AsyncMock,
            side_effect=[False, True],
        ),
        patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock, return_value=False),
    ):
        await update_tag_if_needed(AsyncMock(), db_session, uc, chat, 1)

    assert uc.reputation_level == 1
    assert uc.tag is None


async def test_level_kept_on_transient_failure(db_session, chat, user):
    """Временный сбой: уровень не фиксируем, следующее сообщение повторит попытку."""
    uc = await _make_user_chat(db_session, user.id, chat.id)

    with (
        patch("app.services.tag_service.tag_calls_blocked", new_callable=AsyncMock, return_value=False),
        patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock, return_value=False),
    ):
        await update_tag_if_needed(AsyncMock(), db_session, uc, chat, 1)

    assert uc.reputation_level == 0
    assert uc.tag is None


async def test_no_repeated_level_up_when_permission_missing(db_session, chat, user):
    """Уровень уже зафиксирован — уровень не должен начисляться заново каждое сообщение."""
    uc = await _make_user_chat(db_session, user.id, chat.id, reputation_score=49)

    with (
        patch("app.services.tag_service.tag_calls_blocked", new_callable=AsyncMock, return_value=True),
        patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock) as mock_set,
    ):
        first_level = await add_message_score(db_session, uc, chat)
        assert first_level == 1

        await update_tag_if_needed(AsyncMock(), db_session, uc, chat, first_level)
        assert first_level is not None
        assert uc.reputation_level == 1

        assert await add_message_score(db_session, uc, chat) is None

    mock_set.assert_not_called()
