"""Integration tests for audit_service."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Chat
from app.db.models.settings_audit import SettingsAuditLog
from app.services.audit_service import (
    FIELD_SECTION_MAP,
    check_section_access,
    get_audit_log,
    record_settings_changes,
)
from tests.factories import create_chat, create_user


@pytest.fixture
async def chat(db_session: AsyncSession):
    return await create_chat(db_session)


@pytest.fixture
async def user(db_session: AsyncSession):
    return await create_user(db_session)


# ── record_settings_changes ──────────────────────────────────────────────────


async def test_record_single_field_change(db_session, chat, user):
    await record_settings_changes(
        db_session, chat, user.id, {"warn_limit": 5}
    )
    await db_session.commit()

    entries, total = await get_audit_log(db_session, chat.id)
    assert total == 1
    assert entries[0].section == "moderation"
    assert entries[0].user_id == user.id
    assert len(entries[0].changes) == 1
    assert entries[0].changes[0]["field"] == "warn_limit"
    assert entries[0].changes[0]["old"] == 3  # default
    assert entries[0].changes[0]["new"] == 5


async def test_record_multiple_fields_same_section(db_session, chat, user):
    await record_settings_changes(
        db_session,
        chat,
        user.id,
        {"warn_limit": 10, "warn_punishment": "mute"},
    )
    await db_session.commit()

    entries, total = await get_audit_log(db_session, chat.id)
    assert total == 1
    assert entries[0].section == "moderation"
    assert len(entries[0].changes) == 2
    fields = {c["field"] for c in entries[0].changes}
    assert fields == {"warn_limit", "warn_punishment"}


async def test_record_fields_across_sections(db_session, chat, user):
    await record_settings_changes(
        db_session,
        chat,
        user.id,
        {"warn_limit": 5, "captcha_enabled": True},
    )
    await db_session.commit()

    entries, total = await get_audit_log(db_session, chat.id)
    assert total == 2
    sections = {e.section for e in entries}
    assert sections == {"moderation", "captcha"}


async def test_record_skips_unchanged_value(db_session, chat, user):
    # warn_limit defaults to 3; passing 3 should produce no entry
    await record_settings_changes(
        db_session, chat, user.id, {"warn_limit": 3}
    )
    await db_session.commit()

    entries, total = await get_audit_log(db_session, chat.id)
    assert total == 0


async def test_record_skips_unknown_field(db_session, chat, user):
    await record_settings_changes(
        db_session, chat, user.id, {"nonexistent_field": "value"}
    )
    await db_session.commit()

    entries, total = await get_audit_log(db_session, chat.id)
    assert total == 0


async def test_record_serializes_complex_values(db_session, chat, user):
    new_thresholds = [10, 20, 30, 40, 50]
    await record_settings_changes(
        db_session, chat, user.id, {"tags_thresholds": new_thresholds}
    )
    await db_session.commit()

    entries, total = await get_audit_log(db_session, chat.id)
    assert total == 1
    change = entries[0].changes[0]
    assert change["new"] == new_thresholds


async def test_record_none_old_value(db_session, chat, user):
    # tags_custom is None by default
    custom = {"0": "", "1": "Newbie"}
    await record_settings_changes(
        db_session, chat, user.id, {"tags_custom": custom}
    )
    await db_session.commit()

    entries, total = await get_audit_log(db_session, chat.id)
    assert total == 1
    assert entries[0].changes[0]["old"] is None
    assert entries[0].changes[0]["new"] == custom


# ── get_audit_log ────────────────────────────────────────────────────────────


async def test_get_audit_log_empty(db_session, chat):
    entries, total = await get_audit_log(db_session, chat.id)
    assert entries == []
    assert total == 0


async def test_get_audit_log_ordered_desc(db_session, chat, user):
    # Create several entries
    await record_settings_changes(db_session, chat, user.id, {"warn_limit": 5})
    await db_session.commit()
    await record_settings_changes(db_session, chat, user.id, {"warn_limit": 7})
    await db_session.commit()

    entries, total = await get_audit_log(db_session, chat.id)
    assert total == 2
    # Most recent first
    assert entries[0].changes[0]["new"] == 7


async def test_get_audit_log_pagination(db_session, chat, user):
    # Create 5 entries
    for i in range(5):
        await record_settings_changes(
            db_session, chat, user.id, {"warn_limit": i + 10}
        )
        await db_session.commit()
        # Refresh chat to pick up new warn_limit for next iteration's "old" value
        await db_session.refresh(chat)
        chat.warn_limit = i + 10

    entries_p1, total = await get_audit_log(db_session, chat.id, page=1, limit=2)
    assert total == 5
    assert len(entries_p1) == 2

    entries_p2, total = await get_audit_log(db_session, chat.id, page=2, limit=2)
    assert len(entries_p2) == 2

    entries_p3, total = await get_audit_log(db_session, chat.id, page=3, limit=2)
    assert len(entries_p3) == 1


async def test_get_audit_log_isolates_by_chat(db_session, user):
    chat_a = await create_chat(db_session, title="A")
    chat_b = await create_chat(db_session, title="B")

    await record_settings_changes(db_session, chat_a, user.id, {"warn_limit": 5})
    await db_session.commit()
    await record_settings_changes(db_session, chat_b, user.id, {"warn_limit": 10})
    await db_session.commit()

    entries_a, total_a = await get_audit_log(db_session, chat_a.id)
    entries_b, total_b = await get_audit_log(db_session, chat_b.id)
    assert total_a == 1
    assert total_b == 1
    assert entries_a[0].changes[0]["new"] == 5
    assert entries_b[0].changes[0]["new"] == 10


# ── check_section_access ────────────────────────────────────────────────────


def test_check_section_access_creator_always_allowed():
    chat = Chat(id=-1, settings_locked_sections=["moderation", "captcha"])
    blocked = check_section_access(chat, {"warn_limit": 5}, is_creator=True)
    assert blocked == []


def test_check_section_access_no_locked_sections():
    chat = Chat(id=-1, settings_locked_sections=None)
    blocked = check_section_access(chat, {"warn_limit": 5}, is_creator=False)
    assert blocked == []


def test_check_section_access_empty_locked_sections():
    chat = Chat(id=-1, settings_locked_sections=[])
    blocked = check_section_access(chat, {"warn_limit": 5}, is_creator=False)
    assert blocked == []


def test_check_section_access_blocks_locked_field():
    chat = Chat(id=-1, settings_locked_sections=["moderation"])
    blocked = check_section_access(
        chat, {"warn_limit": 5, "captcha_enabled": True}, is_creator=False
    )
    assert blocked == ["warn_limit"]


def test_check_section_access_blocks_multiple_fields():
    chat = Chat(id=-1, settings_locked_sections=["moderation"])
    blocked = check_section_access(
        chat,
        {"warn_limit": 5, "warn_punishment": "mute"},
        is_creator=False,
    )
    assert set(blocked) == {"warn_limit", "warn_punishment"}


def test_check_section_access_unknown_field_not_blocked():
    chat = Chat(id=-1, settings_locked_sections=["moderation"])
    blocked = check_section_access(
        chat, {"unknown_field": "value"}, is_creator=False
    )
    assert blocked == []
