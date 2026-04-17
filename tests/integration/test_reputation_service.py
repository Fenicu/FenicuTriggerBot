"""Integration tests for reputation_service."""

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Chat
from app.db.models.user_chat import UserChat
from app.services.reputation_service import (
    DEFAULT_THRESHOLDS,
    add_message_score,
    add_reaction_score,
    add_reply_score,
    calculate_level,
    get_active_users_count,
    get_level_name,
    get_thresholds,
    get_user_rank,
)
from tests.factories import create_chat, create_user


@pytest.fixture
async def chat(db_session: AsyncSession):
    return await create_chat(db_session, tags_enabled=True)


@pytest.fixture
async def user(db_session: AsyncSession):
    return await create_user(db_session)


@pytest.fixture
async def other_user(db_session: AsyncSession):
    return await create_user(db_session, first_name="Other")


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
    }
    defaults.update(overrides)
    uc = UserChat(**defaults)
    db_session.add(uc)
    await db_session.flush()
    return uc


# ── get_thresholds ───────────────────────────────────────────────────────────


def test_get_thresholds_default():
    chat = Chat(id=-1)
    assert get_thresholds(chat) == DEFAULT_THRESHOLDS


def test_get_thresholds_custom():
    custom = [10, 20, 30, 40, 50]
    chat = Chat(id=-1, tags_thresholds=custom)
    assert get_thresholds(chat) == custom


def test_get_thresholds_invalid_length_falls_back():
    chat = Chat(id=-1, tags_thresholds=[10, 20])
    assert get_thresholds(chat) == DEFAULT_THRESHOLDS


def test_get_thresholds_none_falls_back():
    chat = Chat(id=-1, tags_thresholds=None)
    assert get_thresholds(chat) == DEFAULT_THRESHOLDS


# ── calculate_level ──────────────────────────────────────────────────────────


def test_calculate_level_zero():
    assert calculate_level(0, DEFAULT_THRESHOLDS) == 0


def test_calculate_level_at_threshold():
    assert calculate_level(50, DEFAULT_THRESHOLDS) == 1


def test_calculate_level_between_thresholds():
    assert calculate_level(100, DEFAULT_THRESHOLDS) == 1


def test_calculate_level_max():
    assert calculate_level(5000, DEFAULT_THRESHOLDS) == 5


def test_calculate_level_beyond_max():
    assert calculate_level(99999, DEFAULT_THRESHOLDS) == 5


# ── get_level_name ───────────────────────────────────────────────────────────


def test_get_level_name_neutral_ru():
    chat = Chat(id=-1, tags_preset="neutral", language_code="ru")
    assert get_level_name(0, chat) == ""
    assert get_level_name(1, chat) == "Участник"
    assert get_level_name(5, chat) == "Легенда"


def test_get_level_name_neutral_en():
    chat = Chat(id=-1, tags_preset="neutral", language_code="en")
    assert get_level_name(1, chat) == "Member"
    assert get_level_name(5, chat) == "Legend"


def test_get_level_name_gaming():
    chat = Chat(id=-1, tags_preset="gaming", language_code="ru")
    assert get_level_name(1, chat) == "Бронза"
    assert get_level_name(5, chat) == "Алмаз"


def test_get_level_name_numeric():
    chat = Chat(id=-1, tags_preset="numeric")
    assert get_level_name(1, chat) == "Lv.1"
    assert get_level_name(5, chat) == "Lv.5"


def test_get_level_name_custom_overrides():
    chat = Chat(id=-1, tags_custom={"0": "", "1": "Noob", "5": "God"})
    assert get_level_name(1, chat) == "Noob"
    assert get_level_name(5, chat) == "God"
    # Missing level returns empty string
    assert get_level_name(3, chat) == ""


# ── add_message_score ────────────────────────────────────────────────────────


async def test_add_message_score_increments(db_session, chat, user):
    uc = await _make_user_chat(db_session, user.id, chat.id)

    result = await add_message_score(db_session, uc, chat)

    assert uc.reputation_score == chat.tags_weight_messages
    assert uc.daily_message_count == 1


async def test_add_message_score_resets_daily_counter(db_session, chat, user):
    uc = await _make_user_chat(
        db_session,
        user.id,
        chat.id,
        daily_message_date=date(2020, 1, 1),
        daily_message_count=999,
    )

    await add_message_score(db_session, uc, chat)

    assert uc.daily_message_date == date.today()
    assert uc.daily_message_count == 1


async def test_add_message_score_respects_daily_limit(db_session, chat, user):
    uc = await _make_user_chat(
        db_session,
        user.id,
        chat.id,
        daily_message_date=date.today(),
        daily_message_count=chat.tags_daily_message_limit,
    )

    result = await add_message_score(db_session, uc, chat)
    assert result is None
    assert uc.reputation_score == 0


async def test_add_message_score_returns_new_level(db_session, chat, user):
    # Set score just below level 1 threshold
    thresholds = get_thresholds(chat)
    uc = await _make_user_chat(
        db_session,
        user.id,
        chat.id,
        reputation_score=thresholds[0] - chat.tags_weight_messages,
    )

    result = await add_message_score(db_session, uc, chat)
    assert result == 1
    assert uc.reputation_level == 1


async def test_add_message_score_no_level_change(db_session, chat, user):
    uc = await _make_user_chat(db_session, user.id, chat.id, reputation_score=0)

    result = await add_message_score(db_session, uc, chat)
    # Score 1 is below threshold 50, still level 0 -> no change
    assert result is None


# ── add_reaction_score ───────────────────────────────────────────────────────


async def test_add_reaction_score_increments_target(db_session, chat, user, other_user):
    uc = await _make_user_chat(db_session, other_user.id, chat.id)
    # Also need from_user in user_chats for the log, but not required by the service
    # The service only looks up the target user_chat

    result = await add_reaction_score(db_session, chat, user.id, other_user.id, chat.id)

    assert uc.reputation_score == chat.tags_weight_reactions


async def test_add_reaction_score_self_reaction_ignored(db_session, chat, user):
    uc = await _make_user_chat(db_session, user.id, chat.id)

    result = await add_reaction_score(db_session, chat, user.id, user.id, chat.id)
    assert result is None
    assert uc.reputation_score == 0


async def test_add_reaction_score_daily_limit(db_session, chat, user, other_user):
    uc = await _make_user_chat(db_session, other_user.id, chat.id)

    # Exhaust the daily limit
    for _ in range(chat.tags_daily_reaction_limit):
        await add_reaction_score(db_session, chat, user.id, other_user.id, chat.id)

    score_before = uc.reputation_score
    result = await add_reaction_score(db_session, chat, user.id, other_user.id, chat.id)
    assert result is None
    assert uc.reputation_score == score_before


async def test_add_reaction_score_nonexistent_target(db_session, chat, user):
    # Target user has no UserChat record
    result = await add_reaction_score(db_session, chat, user.id, 999_999, chat.id)
    assert result is None


# ── add_reply_score ──────────────────────────────────────────────────────────


async def test_add_reply_score_increments_target(db_session, chat, user, other_user):
    uc = await _make_user_chat(db_session, other_user.id, chat.id)

    await add_reply_score(db_session, chat, user.id, other_user.id, chat.id)

    assert uc.reputation_score == chat.tags_weight_replies


async def test_add_reply_score_self_reply_ignored(db_session, chat, user):
    uc = await _make_user_chat(db_session, user.id, chat.id)

    result = await add_reply_score(db_session, chat, user.id, user.id, chat.id)
    assert result is None
    assert uc.reputation_score == 0


# ── get_user_rank ────────────────────────────────────────────────────────────


async def test_get_user_rank_single_user(db_session, chat, user):
    await _make_user_chat(db_session, user.id, chat.id, reputation_score=100)

    rank = await get_user_rank(db_session, chat.id, user.id)
    assert rank == 1


async def test_get_user_rank_multiple_users(db_session, chat, user, other_user):
    await _make_user_chat(db_session, user.id, chat.id, reputation_score=50)
    await _make_user_chat(db_session, other_user.id, chat.id, reputation_score=100)

    rank_user = await get_user_rank(db_session, chat.id, user.id)
    rank_other = await get_user_rank(db_session, chat.id, other_user.id)
    assert rank_other == 1
    assert rank_user == 2


async def test_get_user_rank_nonexistent(db_session, chat):
    rank = await get_user_rank(db_session, chat.id, 999_999)
    assert rank is None


async def test_get_user_rank_inactive_excluded(db_session, chat, user, other_user):
    await _make_user_chat(db_session, user.id, chat.id, reputation_score=50, is_active=False)
    await _make_user_chat(db_session, other_user.id, chat.id, reputation_score=100)

    # Inactive user should not appear in ranking
    rank = await get_user_rank(db_session, chat.id, user.id)
    assert rank is None

    rank_other = await get_user_rank(db_session, chat.id, other_user.id)
    assert rank_other == 1


# ── get_active_users_count ───────────────────────────────────────────────────


async def test_get_active_users_count_empty(db_session, chat):
    count = await get_active_users_count(db_session, chat.id)
    assert count == 0


async def test_get_active_users_count_with_users(db_session, chat, user, other_user):
    await _make_user_chat(db_session, user.id, chat.id)
    await _make_user_chat(db_session, other_user.id, chat.id)

    count = await get_active_users_count(db_session, chat.id)
    assert count == 2


async def test_get_active_users_count_excludes_inactive(db_session, chat, user, other_user):
    await _make_user_chat(db_session, user.id, chat.id, is_active=True)
    await _make_user_chat(db_session, other_user.id, chat.id, is_active=False)

    count = await get_active_users_count(db_session, chat.id)
    assert count == 1
