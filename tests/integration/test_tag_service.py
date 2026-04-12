"""Integration tests for tag_service.

The tag_service functions (update_tag_if_needed, set_manual_tag, clear_manual_tag)
depend on a Telegram Bot instance to call the setChatMemberTag API.
We mock the bot and test the database state changes.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models.chat import Chat
from app.db.models.user_chat import UserChat
from app.services.tag_service import (
    clear_manual_tag,
    set_manual_tag,
    update_tag_if_needed,
)
from tests.factories import create_chat, create_user


async def _make_user_chat(
    db_session: AsyncSession,
    user_id: int,
    chat_id: int,
    **overrides,
) -> UserChat:
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
    return await create_chat(
        db_session,
        tags_enabled=True,
        tags_preset="neutral",
        language_code="ru",
    )


@pytest.fixture
async def user(db_session: AsyncSession):
    return await create_user(db_session)


@pytest.fixture
def mock_bot():
    bot = MagicMock()
    return bot


# ── update_tag_if_needed ─────────────────────────────────────────────────────


async def test_update_tag_sets_level_name(db_session, chat, user, mock_bot):
    uc = await _make_user_chat(db_session, user.id, chat.id)
    mock_bot.__call__ = AsyncMock(return_value=True)

    with patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock, return_value=True):
        await update_tag_if_needed(mock_bot, db_session, uc, chat, 1)

    assert uc.tag == "Участник"


async def test_update_tag_skips_manual_tag(db_session, chat, user, mock_bot):
    uc = await _make_user_chat(
        db_session, user.id, chat.id, tag="VIP", tag_is_manual=True
    )

    with patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock) as mock_set:
        await update_tag_if_needed(mock_bot, db_session, uc, chat, 1)

    assert uc.tag == "VIP"
    mock_set.assert_not_called()


async def test_update_tag_skips_same_tag(db_session, chat, user, mock_bot):
    uc = await _make_user_chat(
        db_session, user.id, chat.id, tag="Участник"
    )

    with patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock) as mock_set:
        await update_tag_if_needed(mock_bot, db_session, uc, chat, 1)

    mock_set.assert_not_called()


async def test_update_tag_reverts_on_api_failure(db_session, chat, user, mock_bot):
    uc = await _make_user_chat(db_session, user.id, chat.id, tag="Old")

    with patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock, return_value=False):
        await update_tag_if_needed(mock_bot, db_session, uc, chat, 1)

    assert uc.tag == "Old"


async def test_update_tag_level_zero_clears(db_session, chat, user, mock_bot):
    uc = await _make_user_chat(
        db_session, user.id, chat.id, tag="Участник"
    )

    with patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock, return_value=True):
        await update_tag_if_needed(mock_bot, db_session, uc, chat, 0)

    # Level 0 has empty name in neutral preset
    assert uc.tag is None


# ── set_manual_tag ───────────────────────────────────────────────────────────


async def test_set_manual_tag_success(db_session, chat, user, mock_bot):
    uc = await _make_user_chat(db_session, user.id, chat.id)

    with patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock, return_value=True):
        result = await set_manual_tag(mock_bot, db_session, uc, chat.id, "Admin")

    assert result is True
    assert uc.tag == "Admin"
    assert uc.tag_is_manual is True


async def test_set_manual_tag_truncates_to_16(db_session, chat, user, mock_bot):
    uc = await _make_user_chat(db_session, user.id, chat.id)
    long_tag = "A" * 30

    with patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock, return_value=True):
        await set_manual_tag(mock_bot, db_session, uc, chat.id, long_tag)

    assert len(uc.tag) == 16


async def test_set_manual_tag_none_clears(db_session, chat, user, mock_bot):
    uc = await _make_user_chat(
        db_session, user.id, chat.id, tag="VIP", tag_is_manual=True
    )

    with patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock, return_value=True):
        result = await set_manual_tag(mock_bot, db_session, uc, chat.id, None)

    assert result is True
    assert uc.tag is None
    assert uc.tag_is_manual is False


async def test_set_manual_tag_rollback_on_failure(db_session, chat, user, mock_bot):
    uc = await _make_user_chat(
        db_session, user.id, chat.id, tag="Old", tag_is_manual=False
    )

    with patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock, return_value=False):
        with patch.object(db_session, "rollback", new_callable=AsyncMock) as mock_rollback:
            result = await set_manual_tag(mock_bot, db_session, uc, chat.id, "New")

    assert result is False
    assert uc.tag == "Old"
    assert uc.tag_is_manual is False


# ── clear_manual_tag ─────────────────────────────────────────────────────────


async def test_clear_manual_tag_restores_auto(db_session, chat, user, mock_bot):
    uc = await _make_user_chat(
        db_session,
        user.id,
        chat.id,
        tag="VIP",
        tag_is_manual=True,
        reputation_level=2,
    )

    with patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock, return_value=True):
        result = await clear_manual_tag(mock_bot, db_session, uc, chat)

    assert result is True
    assert uc.tag_is_manual is False
    # Level 2 in neutral/ru = "Активный"
    assert uc.tag == "Активный"


async def test_clear_manual_tag_level_zero(db_session, chat, user, mock_bot):
    uc = await _make_user_chat(
        db_session,
        user.id,
        chat.id,
        tag="VIP",
        tag_is_manual=True,
        reputation_level=0,
    )

    with patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock, return_value=True):
        result = await clear_manual_tag(mock_bot, db_session, uc, chat)

    assert result is True
    assert uc.tag is None
    assert uc.tag_is_manual is False


async def test_clear_manual_tag_rollback_on_failure(db_session, chat, user, mock_bot):
    uc = await _make_user_chat(
        db_session,
        user.id,
        chat.id,
        tag="VIP",
        tag_is_manual=True,
        reputation_level=1,
    )

    with patch("app.services.tag_service._set_chat_member_tag", new_callable=AsyncMock, return_value=False):
        with patch.object(db_session, "rollback", new_callable=AsyncMock):
            result = await clear_manual_tag(mock_bot, db_session, uc, chat)

    assert result is False
    assert uc.tag == "VIP"
    assert uc.tag_is_manual is True
