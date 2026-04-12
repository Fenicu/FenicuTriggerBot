"""Integration tests for ModerationService."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.moderation_service import ModerationService
from tests.factories import create_chat, create_user


@pytest.fixture
async def chat(db_session: AsyncSession):
    return await create_chat(db_session)


@pytest.fixture
async def user(db_session: AsyncSession):
    return await create_user(db_session)


@pytest.fixture
async def admin(db_session: AsyncSession):
    return await create_user(db_session, first_name="Admin")


@pytest.fixture
def svc(db_session: AsyncSession) -> ModerationService:
    return ModerationService(db_session)


# ── add_warn ─────────────────────────────────────────────────────────────────


async def test_add_warn_creates_record(svc, chat, user, admin):
    warn = await svc.add_warn(chat.id, user.id, admin.id, "spam")

    assert warn.id is not None
    assert warn.chat_id == chat.id
    assert warn.user_id == user.id
    assert warn.admin_id == admin.id
    assert warn.reason == "spam"
    assert warn.created_at is not None


async def test_add_warn_with_none_reason(svc, chat, user, admin):
    warn = await svc.add_warn(chat.id, user.id, admin.id, None)

    assert warn.reason is None


async def test_add_multiple_warns(svc, chat, user, admin):
    w1 = await svc.add_warn(chat.id, user.id, admin.id, "first")
    w2 = await svc.add_warn(chat.id, user.id, admin.id, "second")
    w3 = await svc.add_warn(chat.id, user.id, admin.id, "third")

    assert w1.id != w2.id != w3.id
    warns = await svc.get_user_warns(chat.id, user.id)
    assert len(warns) == 3


# ── get_user_warns ───────────────────────────────────────────────────────────


async def test_get_user_warns_empty(svc, chat, user):
    warns = await svc.get_user_warns(chat.id, user.id)
    assert warns == []


async def test_get_user_warns_returns_ordered(svc, chat, user, admin):
    await svc.add_warn(chat.id, user.id, admin.id, "first")
    await svc.add_warn(chat.id, user.id, admin.id, "second")

    warns = await svc.get_user_warns(chat.id, user.id)
    assert len(warns) == 2
    assert warns[0].reason == "first"
    assert warns[1].reason == "second"


async def test_get_user_warns_isolates_by_chat(svc, db_session, user, admin):
    chat_a = await create_chat(db_session, title="Chat A")
    chat_b = await create_chat(db_session, title="Chat B")

    await svc.add_warn(chat_a.id, user.id, admin.id, "in A")
    await svc.add_warn(chat_b.id, user.id, admin.id, "in B")

    warns_a = await svc.get_user_warns(chat_a.id, user.id)
    warns_b = await svc.get_user_warns(chat_b.id, user.id)
    assert len(warns_a) == 1
    assert len(warns_b) == 1
    assert warns_a[0].reason == "in A"


async def test_get_user_warns_isolates_by_user(svc, chat, admin, db_session):
    user_a = await create_user(db_session, first_name="Alice")
    user_b = await create_user(db_session, first_name="Bob")

    await svc.add_warn(chat.id, user_a.id, admin.id, "Alice warn")
    await svc.add_warn(chat.id, user_b.id, admin.id, "Bob warn")

    warns_a = await svc.get_user_warns(chat.id, user_a.id)
    assert len(warns_a) == 1
    assert warns_a[0].reason == "Alice warn"


# ── get_warn_count ───────────────────────────────────────────────────────────


async def test_get_warn_count_zero(svc, chat, user):
    count = await svc.get_warn_count(chat.id, user.id)
    assert count == 0


async def test_get_warn_count_after_adding(svc, chat, user, admin):
    await svc.add_warn(chat.id, user.id, admin.id, "one")
    await svc.add_warn(chat.id, user.id, admin.id, "two")

    count = await svc.get_warn_count(chat.id, user.id)
    assert count == 2


# ── remove_last_warn ─────────────────────────────────────────────────────────


async def test_remove_last_warn_returns_true(svc, chat, user, admin):
    await svc.add_warn(chat.id, user.id, admin.id, "first")
    await svc.add_warn(chat.id, user.id, admin.id, "second")

    removed = await svc.remove_last_warn(chat.id, user.id)
    assert removed is True

    warns = await svc.get_user_warns(chat.id, user.id)
    assert len(warns) == 1
    assert warns[0].reason == "first"


async def test_remove_last_warn_empty_returns_false(svc, chat, user):
    removed = await svc.remove_last_warn(chat.id, user.id)
    assert removed is False


async def test_remove_last_warn_successive(svc, chat, user, admin):
    await svc.add_warn(chat.id, user.id, admin.id, "only one")

    assert await svc.remove_last_warn(chat.id, user.id) is True
    assert await svc.remove_last_warn(chat.id, user.id) is False

    count = await svc.get_warn_count(chat.id, user.id)
    assert count == 0


# ── reset_warns ──────────────────────────────────────────────────────────────


async def test_reset_warns_clears_all(svc, chat, user, admin):
    await svc.add_warn(chat.id, user.id, admin.id, "a")
    await svc.add_warn(chat.id, user.id, admin.id, "b")
    await svc.add_warn(chat.id, user.id, admin.id, "c")

    await svc.reset_warns(chat.id, user.id)

    count = await svc.get_warn_count(chat.id, user.id)
    assert count == 0


async def test_reset_warns_on_empty_is_noop(svc, chat, user):
    # Should not raise
    await svc.reset_warns(chat.id, user.id)
    count = await svc.get_warn_count(chat.id, user.id)
    assert count == 0


async def test_reset_warns_only_affects_target_user(svc, chat, admin, db_session):
    user_a = await create_user(db_session, first_name="Alice")
    user_b = await create_user(db_session, first_name="Bob")

    await svc.add_warn(chat.id, user_a.id, admin.id, "A warn")
    await svc.add_warn(chat.id, user_b.id, admin.id, "B warn")

    await svc.reset_warns(chat.id, user_a.id)

    assert await svc.get_warn_count(chat.id, user_a.id) == 0
    assert await svc.get_warn_count(chat.id, user_b.id) == 1


# ── get_chat_settings / update_chat_settings ─────────────────────────────────


async def test_get_chat_settings_existing(svc, chat):
    settings = await svc.get_chat_settings(chat.id)
    assert settings.id == chat.id
    assert settings.warn_limit == 3  # default


async def test_get_chat_settings_nonexistent_returns_default(svc):
    settings = await svc.get_chat_settings(999_999_999)
    assert settings.id == 999_999_999
    # Chat(id=...) doesn't apply column defaults, so warn_limit is None
    assert settings.warn_limit is None


async def test_update_chat_settings_warn_limit(svc, chat):
    updated = await svc.update_chat_settings(chat.id, warn_limit=5)
    assert updated.warn_limit == 5


async def test_update_chat_settings_warn_punishment(svc, chat):
    updated = await svc.update_chat_settings(chat.id, warn_punishment="mute")
    assert updated.warn_punishment == "mute"


async def test_update_chat_settings_creates_chat_if_missing(svc, db_session):
    new_chat_id = -999_888_777
    updated = await svc.update_chat_settings(new_chat_id, warn_limit=10)
    assert updated.id == new_chat_id
    assert updated.warn_limit == 10
