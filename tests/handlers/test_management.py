"""Tests for app/bot/handlers/management.py — trigger edit callbacks."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.callback_data.triggers import TriggerEditCallback
from app.db.models.trigger import AccessLevel, MatchType, Trigger
from tests.factories import create_chat, create_trigger, create_user
from tests.handlers.conftest import _make_callback


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
async def chat(db_session: AsyncSession):
    return await create_chat(db_session)


@pytest.fixture
async def user(db_session: AsyncSession):
    return await create_user(db_session, username="creator")


@pytest.fixture
async def trigger(db_session: AsyncSession, chat, user):
    return await create_trigger(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        key_phrase="test_edit_key",
    )


def _make_i18n():
    """Create a comprehensive mock i18n for management handler."""
    i18n = MagicMock()

    # Trigger edit details
    i18n.trigger.edit.title.return_value = "Edit Trigger"
    i18n.trigger.edit.key.return_value = "Key: test"
    i18n.trigger.edit.type.return_value = "Type: exact"
    i18n.trigger.edit.case.return_value = "Case: insensitive"
    i18n.trigger.edit.access.return_value = "Access: all"
    i18n.trigger.edit.template.return_value = "Template: no"
    i18n.trigger.edit.created.return_value = "Created by: user"
    i18n.trigger.edit.stats.return_value = "Uses: 0"

    # Values
    i18n.val.case.sensitive.return_value = "sensitive"
    i18n.val.case.insensitive.return_value = "insensitive"
    i18n.val.access.all.return_value = "all"
    i18n.val.access.admins.return_value = "admins"
    i18n.val.access.owner.return_value = "owner"
    i18n.val.template.true.return_value = "yes"
    i18n.val.template.false.return_value = "no"

    # Buttons
    i18n.btn.case.sensitive.return_value = "Case: ON"
    i18n.btn.case.insensitive.return_value = "Case: OFF"
    i18n.btn.matchtype.exact.return_value = "Type: exact"
    i18n.btn.matchtype.contains.return_value = "Type: contains"
    i18n.btn.matchtype.regexp.return_value = "Type: regexp"
    i18n.btn.access.all.return_value = "Access: all"
    i18n.btn.access.admins.return_value = "Access: admins"
    i18n.btn.access.owner.return_value = "Access: owner"
    i18n.btn.template.true.return_value = "Template: ON"
    i18n.btn.template.false.return_value = "Template: OFF"
    i18n.btn.delete.return_value = "Delete"
    i18n.btn.back.return_value = "Back"

    # Misc
    i18n.trigger.missing.return_value = "Trigger not found"
    i18n.error.permission.denied.return_value = "Permission denied"
    i18n.trigger.deleted.return_value = "Trigger deleted"
    i18n.confirm.delete.return_value = "Are you sure?"
    i18n.trigger.list.empty.return_value = "No triggers"
    i18n.trigger.list.header.return_value = "Triggers"
    i18n.trigger.list.page.return_value = "Page 1/1"
    i18n.action.yes.return_value = "Yes"
    i18n.action.cancel.return_value = "Cancel"

    return i18n


def _make_bot_mock(is_admin: bool = True, creator_name: str = "creator"):
    """Create a mock Bot for management handler."""
    bot = MagicMock()
    member = MagicMock()
    member.status = "administrator" if is_admin else "member"
    bot.get_chat_member = AsyncMock(return_value=member)

    chat_info = MagicMock()
    chat_info.username = creator_name
    chat_info.full_name = creator_name
    bot.get_chat = AsyncMock(return_value=chat_info)

    return bot


# ── toggle_case ─────────────────────────────────────────────────────────────


async def test_toggle_case_on(db_session: AsyncSession, trigger, chat, user):
    from app.bot.handlers.management import on_trigger_edit

    callback_data = TriggerEditCallback(id=trigger.id, action="toggle_case")
    callback = _make_callback("", user_id=user.id, chat_id=chat.id)
    bot = _make_bot_mock(is_admin=True)
    i18n = _make_i18n()

    await on_trigger_edit(callback, callback_data, db_session, bot, i18n)

    await db_session.refresh(trigger)
    assert trigger.is_case_sensitive is True


async def test_toggle_case_off(db_session: AsyncSession, chat, user):
    from app.bot.handlers.management import on_trigger_edit

    t = await create_trigger(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        is_case_sensitive=True,
        key_phrase="case_test",
    )

    callback_data = TriggerEditCallback(id=t.id, action="toggle_case")
    callback = _make_callback("", user_id=user.id, chat_id=chat.id)
    bot = _make_bot_mock(is_admin=True)
    i18n = _make_i18n()

    await on_trigger_edit(callback, callback_data, db_session, bot, i18n)

    await db_session.refresh(t)
    assert t.is_case_sensitive is False


# ── toggle_type ─────────────────────────────────────────────────────────────


async def test_toggle_type_exact_to_contains(db_session: AsyncSession, trigger, chat, user):
    from app.bot.handlers.management import on_trigger_edit

    assert trigger.match_type == MatchType.EXACT

    callback_data = TriggerEditCallback(id=trigger.id, action="toggle_type")
    callback = _make_callback("", user_id=user.id, chat_id=chat.id)
    bot = _make_bot_mock()
    i18n = _make_i18n()

    await on_trigger_edit(callback, callback_data, db_session, bot, i18n)

    await db_session.refresh(trigger)
    assert trigger.match_type == MatchType.CONTAINS


async def test_toggle_type_contains_to_regexp(db_session: AsyncSession, chat, user):
    from app.bot.handlers.management import on_trigger_edit

    t = await create_trigger(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        match_type=MatchType.CONTAINS,
        key_phrase="valid_regex",
    )

    callback_data = TriggerEditCallback(id=t.id, action="toggle_type")
    callback = _make_callback("", user_id=user.id, chat_id=chat.id)
    bot = _make_bot_mock()
    i18n = _make_i18n()

    await on_trigger_edit(callback, callback_data, db_session, bot, i18n)

    await db_session.refresh(t)
    assert t.match_type == MatchType.REGEXP


async def test_toggle_type_regexp_to_exact(db_session: AsyncSession, chat, user):
    from app.bot.handlers.management import on_trigger_edit

    t = await create_trigger(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        match_type=MatchType.REGEXP,
        key_phrase="some_pattern",
    )

    callback_data = TriggerEditCallback(id=t.id, action="toggle_type")
    callback = _make_callback("", user_id=user.id, chat_id=chat.id)
    bot = _make_bot_mock()
    i18n = _make_i18n()

    await on_trigger_edit(callback, callback_data, db_session, bot, i18n)

    await db_session.refresh(t)
    assert t.match_type == MatchType.EXACT


async def test_toggle_type_to_regexp_invalid_regex_blocked(db_session: AsyncSession, chat, user):
    """Switching to regexp with an invalid regex pattern should be blocked."""
    from app.bot.handlers.management import on_trigger_edit

    t = await create_trigger(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        match_type=MatchType.CONTAINS,
        key_phrase="[invalid(",
    )

    callback_data = TriggerEditCallback(id=t.id, action="toggle_type")
    callback = _make_callback("", user_id=user.id, chat_id=chat.id)
    bot = _make_bot_mock()
    i18n = _make_i18n()

    await on_trigger_edit(callback, callback_data, db_session, bot, i18n)

    # Should remain CONTAINS because the regex is invalid
    await db_session.refresh(t)
    assert t.match_type == MatchType.CONTAINS
    # The handler calls callback.answer(regex_error, show_alert=True) and returns
    assert callback.answer.await_count >= 1
    # Verify show_alert=True was passed
    first_call = callback.answer.await_args_list[0]
    assert first_call.kwargs.get("show_alert") is True


# ── toggle_access ───────────────────────────────────────────────────────────


async def test_toggle_access_all_to_admins(db_session: AsyncSession, trigger, chat, user):
    from app.bot.handlers.management import on_trigger_edit

    assert trigger.access_level == AccessLevel.ALL

    callback_data = TriggerEditCallback(id=trigger.id, action="toggle_access")
    callback = _make_callback("", user_id=user.id, chat_id=chat.id)
    bot = _make_bot_mock()
    i18n = _make_i18n()

    await on_trigger_edit(callback, callback_data, db_session, bot, i18n)

    await db_session.refresh(trigger)
    assert trigger.access_level == AccessLevel.ADMINS


async def test_toggle_access_admins_to_owner(db_session: AsyncSession, chat, user):
    from app.bot.handlers.management import on_trigger_edit

    t = await create_trigger(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        access_level=AccessLevel.ADMINS,
        key_phrase="admin_access",
    )

    callback_data = TriggerEditCallback(id=t.id, action="toggle_access")
    callback = _make_callback("", user_id=user.id, chat_id=chat.id)
    bot = _make_bot_mock()
    i18n = _make_i18n()

    await on_trigger_edit(callback, callback_data, db_session, bot, i18n)

    await db_session.refresh(t)
    assert t.access_level == AccessLevel.OWNER


async def test_toggle_access_owner_to_all(db_session: AsyncSession, chat, user):
    from app.bot.handlers.management import on_trigger_edit

    t = await create_trigger(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        access_level=AccessLevel.OWNER,
        key_phrase="owner_access",
    )

    callback_data = TriggerEditCallback(id=t.id, action="toggle_access")
    callback = _make_callback("", user_id=user.id, chat_id=chat.id)
    bot = _make_bot_mock()
    i18n = _make_i18n()

    await on_trigger_edit(callback, callback_data, db_session, bot, i18n)

    await db_session.refresh(t)
    assert t.access_level == AccessLevel.ALL


# ── toggle_template ─────────────────────────────────────────────────────────


async def test_toggle_template_on(db_session: AsyncSession, trigger, chat, user):
    from app.bot.handlers.management import on_trigger_edit

    assert trigger.is_template is False

    callback_data = TriggerEditCallback(id=trigger.id, action="toggle_template")
    callback = _make_callback("", user_id=user.id, chat_id=chat.id)
    bot = _make_bot_mock()
    i18n = _make_i18n()

    await on_trigger_edit(callback, callback_data, db_session, bot, i18n)

    await db_session.refresh(trigger)
    assert trigger.is_template is True


async def test_toggle_template_off(db_session: AsyncSession, chat, user):
    from app.bot.handlers.management import on_trigger_edit

    t = await create_trigger(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        is_template=True,
        key_phrase="template_test",
    )

    callback_data = TriggerEditCallback(id=t.id, action="toggle_template")
    callback = _make_callback("", user_id=user.id, chat_id=chat.id)
    bot = _make_bot_mock()
    i18n = _make_i18n()

    await on_trigger_edit(callback, callback_data, db_session, bot, i18n)

    await db_session.refresh(t)
    assert t.is_template is False


# ── delete_confirm ──────────────────────────────────────────────────────────


async def test_delete_confirm(db_session: AsyncSession, trigger, chat, user):
    from app.bot.handlers.management import on_trigger_edit

    callback_data = TriggerEditCallback(id=trigger.id, action="delete_confirm")
    callback = _make_callback("", user_id=user.id, chat_id=chat.id)
    bot = _make_bot_mock()
    i18n = _make_i18n()

    await on_trigger_edit(callback, callback_data, db_session, bot, i18n)

    await db_session.refresh(trigger)
    assert trigger.is_deleted is True
    callback.answer.assert_any_await(i18n.trigger.deleted())


async def test_delete_ask_shows_confirmation(db_session: AsyncSession, trigger, chat, user):
    from app.bot.handlers.management import on_trigger_edit

    callback_data = TriggerEditCallback(id=trigger.id, action="delete_ask")
    callback = _make_callback("", user_id=user.id, chat_id=chat.id)
    bot = _make_bot_mock()
    i18n = _make_i18n()

    await on_trigger_edit(callback, callback_data, db_session, bot, i18n)

    # Should show confirmation dialog — message edit_text was called
    callback.message.edit_text.assert_awaited_once()


# ── Permission checks ──────────────────────────────────────────────────────


async def test_non_admin_non_creator_cannot_edit(db_session: AsyncSession, trigger, chat):
    from app.bot.handlers.management import on_trigger_edit

    other_user = await create_user(db_session, first_name="Other")

    callback_data = TriggerEditCallback(id=trigger.id, action="toggle_case")
    callback = _make_callback("", user_id=other_user.id, chat_id=chat.id)
    bot = _make_bot_mock(is_admin=False)
    i18n = _make_i18n()

    await on_trigger_edit(callback, callback_data, db_session, bot, i18n)

    callback.answer.assert_any_await(i18n.error.permission.denied(), show_alert=True)


async def test_creator_can_edit_without_admin(db_session: AsyncSession, trigger, chat, user):
    from app.bot.handlers.management import on_trigger_edit

    callback_data = TriggerEditCallback(id=trigger.id, action="toggle_case")
    callback = _make_callback("", user_id=user.id, chat_id=chat.id)
    bot = _make_bot_mock(is_admin=False)  # Not admin but is creator
    i18n = _make_i18n()

    await on_trigger_edit(callback, callback_data, db_session, bot, i18n)

    await db_session.refresh(trigger)
    assert trigger.is_case_sensitive is True  # Toggle succeeded


# ── Missing trigger ─────────────────────────────────────────────────────────


async def test_edit_missing_trigger(db_session: AsyncSession, chat, user):
    from app.bot.handlers.management import on_trigger_edit

    callback_data = TriggerEditCallback(id=999999, action="toggle_case")
    callback = _make_callback("", user_id=user.id, chat_id=chat.id)
    bot = _make_bot_mock()
    i18n = _make_i18n()

    await on_trigger_edit(callback, callback_data, db_session, bot, i18n)

    callback.answer.assert_any_await(i18n.trigger.missing(), show_alert=True)


# ── Open action ─────────────────────────────────────────────────────────────


async def test_open_trigger_details(db_session: AsyncSession, trigger, chat, user):
    """Open action should show trigger details without modifying anything."""
    from app.bot.handlers.management import on_trigger_edit

    callback_data = TriggerEditCallback(id=trigger.id, action="open")
    callback = _make_callback("", user_id=user.id, chat_id=chat.id)
    bot = _make_bot_mock()
    i18n = _make_i18n()

    original_case = trigger.is_case_sensitive
    original_type = trigger.match_type

    await on_trigger_edit(callback, callback_data, db_session, bot, i18n)

    await db_session.refresh(trigger)
    assert trigger.is_case_sensitive == original_case
    assert trigger.match_type == original_type
    callback.message.edit_text.assert_awaited_once()


async def test_open_allowed_for_any_user(db_session: AsyncSession, trigger, chat):
    """Open action should be allowed for any user, not just admin/creator."""
    from app.bot.handlers.management import on_trigger_edit

    other_user = await create_user(db_session, first_name="Viewer")

    callback_data = TriggerEditCallback(id=trigger.id, action="open")
    callback = _make_callback("", user_id=other_user.id, chat_id=chat.id)
    bot = _make_bot_mock(is_admin=False)
    i18n = _make_i18n()

    await on_trigger_edit(callback, callback_data, db_session, bot, i18n)

    # Should not get permission denied
    callback.message.edit_text.assert_awaited_once()
