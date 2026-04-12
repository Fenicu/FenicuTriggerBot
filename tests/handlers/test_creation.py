"""Tests for app/bot/handlers/creation.py — /add command handler."""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Chat
from app.db.models.trigger import AccessLevel, MatchType, ModerationStatus, Trigger
from app.db.models.user import User
from tests.factories import create_chat, create_user


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
async def chat(db_session: AsyncSession):
    return await create_chat(db_session)


@pytest.fixture
async def trusted_chat(db_session: AsyncSession):
    return await create_chat(db_session, is_trusted=True, title="Trusted Chat")


@pytest.fixture
async def admins_only_chat(db_session: AsyncSession):
    return await create_chat(db_session, admins_only_add=True, title="Admins Only")


@pytest.fixture
async def user(db_session: AsyncSession):
    return await create_user(db_session)


@pytest.fixture
async def trusted_user(db_session: AsyncSession):
    return await create_user(db_session, is_trusted=True, first_name="Trusted")


@pytest.fixture
async def moderator_user(db_session: AsyncSession):
    return await create_user(db_session, is_bot_moderator=True, first_name="Moderator")


def _make_i18n():
    """Create a mock i18n TranslatorRunner."""
    i18n = MagicMock()
    i18n.trigger.add.error.return_value = "Add error"
    i18n.add.usage.return_value = "Usage: /add"
    i18n.trigger.added.return_value = "Trigger added"
    i18n.trigger.validation.error.return_value = "Validation error"
    i18n.error.no.rights.return_value = "No rights"
    return i18n


def _make_command(args: str | None = None):
    """Create a mock CommandObject."""
    command = MagicMock()
    command.args = args
    return command


def _make_message(
    chat_id: int,
    user_id: int,
    reply_content: dict | None = None,
    is_admin: bool = False,
):
    """Create a mock Message with reply_to_message."""
    message = MagicMock()
    message.chat = MagicMock()
    message.chat.id = chat_id
    message.from_user = MagicMock()
    message.from_user.id = user_id
    message.answer = AsyncMock()

    if reply_content is not None:
        reply = MagicMock()
        reply.model_dump_json.return_value = json.dumps(reply_content)
        message.reply_to_message = reply
    else:
        message.reply_to_message = None

    # Mock get_member for admin check
    member = MagicMock()
    member.status = "administrator" if is_admin else "member"
    message.chat.get_member = AsyncMock(return_value=member)

    return message


# ── Basic add ───────────────────────────────────────────────────────────────


async def test_add_trigger_basic(db_session: AsyncSession, chat, user):
    from app.bot.handlers.creation import add_trigger

    reply_content = {"text": "Hello world!"}
    message = _make_message(chat.id, user.id, reply_content=reply_content)
    command = _make_command("hello")
    i18n = _make_i18n()

    db_chat = chat
    db_user = user

    await add_trigger(message, command, db_session, i18n, db_chat, db_user)

    # Verify trigger was created
    stmt = select(Trigger).where(Trigger.chat_id == chat.id, Trigger.key_phrase == "hello")
    result = await db_session.execute(stmt)
    trigger = result.scalars().first()

    assert trigger is not None
    assert trigger.match_type == MatchType.EXACT
    assert trigger.is_case_sensitive is False
    assert trigger.access_level == AccessLevel.ALL
    message.answer.assert_awaited_once()


async def test_add_trigger_no_reply(db_session: AsyncSession, chat, user):
    from app.bot.handlers.creation import add_trigger

    message = _make_message(chat.id, user.id, reply_content=None)
    command = _make_command("hello")
    i18n = _make_i18n()

    await add_trigger(message, command, db_session, i18n, chat, user)

    message.answer.assert_awaited_once()
    call_args = message.answer.call_args
    assert call_args.args[0] == "Add error"


async def test_add_trigger_no_args(db_session: AsyncSession, chat, user):
    from app.bot.handlers.creation import add_trigger

    reply_content = {"text": "Content"}
    message = _make_message(chat.id, user.id, reply_content=reply_content)
    command = _make_command(None)
    i18n = _make_i18n()

    await add_trigger(message, command, db_session, i18n, chat, user)

    message.answer.assert_awaited_once()
    assert message.answer.call_args.args[0] == "Usage: /add"


async def test_add_trigger_empty_key_after_flags(db_session: AsyncSession, chat, user):
    """If all args are flags with no key phrase, should error."""
    from app.bot.handlers.creation import add_trigger

    reply_content = {"text": "Content"}
    message = _make_message(chat.id, user.id, reply_content=reply_content)
    command = _make_command("-c -r")
    i18n = _make_i18n()

    await add_trigger(message, command, db_session, i18n, chat, user)

    message.answer.assert_awaited_once()
    assert message.answer.call_args.args[0] == "Add error"


# ── Flags ───────────────────────────────────────────────────────────────────


async def test_add_trigger_case_sensitive_flag(db_session: AsyncSession, chat, user):
    from app.bot.handlers.creation import add_trigger

    reply_content = {"text": "Sensitive content"}
    message = _make_message(chat.id, user.id, reply_content=reply_content)
    command = _make_command("-c CaseSensitiveKey")
    i18n = _make_i18n()

    await add_trigger(message, command, db_session, i18n, chat, user)

    stmt = select(Trigger).where(Trigger.chat_id == chat.id, Trigger.key_phrase == "CaseSensitiveKey")
    result = await db_session.execute(stmt)
    trigger = result.scalars().first()

    assert trigger is not None
    assert trigger.is_case_sensitive is True


async def test_add_trigger_case_sensitive_long_flag(db_session: AsyncSession, chat, user):
    from app.bot.handlers.creation import add_trigger

    reply_content = {"text": "Sensitive"}
    message = _make_message(chat.id, user.id, reply_content=reply_content)
    command = _make_command("--case MyKey")
    i18n = _make_i18n()

    await add_trigger(message, command, db_session, i18n, chat, user)

    stmt = select(Trigger).where(Trigger.chat_id == chat.id)
    result = await db_session.execute(stmt)
    trigger = result.scalars().first()

    assert trigger is not None
    assert trigger.is_case_sensitive is True


async def test_add_trigger_regex_valid(db_session: AsyncSession, chat, user):
    from app.bot.handlers.creation import add_trigger

    reply_content = {"text": "Regex response"}
    message = _make_message(chat.id, user.id, reply_content=reply_content)
    command = _make_command(r"-r hello\d+")
    i18n = _make_i18n()

    await add_trigger(message, command, db_session, i18n, chat, user)

    stmt = select(Trigger).where(Trigger.chat_id == chat.id)
    result = await db_session.execute(stmt)
    trigger = result.scalars().first()

    assert trigger is not None
    assert trigger.match_type == MatchType.REGEXP


async def test_add_trigger_regex_invalid(db_session: AsyncSession, chat, user):
    from app.bot.handlers.creation import add_trigger

    reply_content = {"text": "Regex response"}
    message = _make_message(chat.id, user.id, reply_content=reply_content)
    command = _make_command("-r [invalid(")
    i18n = _make_i18n()

    await add_trigger(message, command, db_session, i18n, chat, user)

    # Should report validation error, no trigger created
    stmt = select(Trigger).where(Trigger.chat_id == chat.id)
    result = await db_session.execute(stmt)
    assert result.scalars().first() is None
    message.answer.assert_awaited_once()


async def test_add_trigger_contains_flag(db_session: AsyncSession, chat, user):
    from app.bot.handlers.creation import add_trigger

    reply_content = {"text": "Contains response"}
    message = _make_message(chat.id, user.id, reply_content=reply_content)
    command = _make_command("-in substring")
    i18n = _make_i18n()

    await add_trigger(message, command, db_session, i18n, chat, user)

    stmt = select(Trigger).where(Trigger.chat_id == chat.id)
    result = await db_session.execute(stmt)
    trigger = result.scalars().first()

    assert trigger is not None
    assert trigger.match_type == MatchType.CONTAINS


async def test_add_trigger_admin_access_flag(db_session: AsyncSession, chat, user):
    from app.bot.handlers.creation import add_trigger

    reply_content = {"text": "Admin only"}
    message = _make_message(chat.id, user.id, reply_content=reply_content)
    command = _make_command("-a admin_trigger")
    i18n = _make_i18n()

    await add_trigger(message, command, db_session, i18n, chat, user)

    stmt = select(Trigger).where(Trigger.chat_id == chat.id)
    result = await db_session.execute(stmt)
    trigger = result.scalars().first()

    assert trigger is not None
    assert trigger.access_level == AccessLevel.ADMINS


async def test_add_trigger_owner_access_flag(db_session: AsyncSession, chat, user):
    from app.bot.handlers.creation import add_trigger

    reply_content = {"text": "Owner only"}
    message = _make_message(chat.id, user.id, reply_content=reply_content)
    command = _make_command("--owner owner_trigger")
    i18n = _make_i18n()

    await add_trigger(message, command, db_session, i18n, chat, user)

    stmt = select(Trigger).where(Trigger.chat_id == chat.id)
    result = await db_session.execute(stmt)
    trigger = result.scalars().first()

    assert trigger is not None
    assert trigger.access_level == AccessLevel.OWNER


async def test_add_trigger_template_flag(db_session: AsyncSession, chat, user):
    from app.bot.handlers.creation import add_trigger

    reply_content = {"text": "Hello {{ user.first_name }}!"}
    message = _make_message(chat.id, user.id, reply_content=reply_content)
    command = _make_command("-t greeting")
    i18n = _make_i18n()

    await add_trigger(message, command, db_session, i18n, chat, user)

    stmt = select(Trigger).where(Trigger.chat_id == chat.id)
    result = await db_session.execute(stmt)
    trigger = result.scalars().first()

    assert trigger is not None
    assert trigger.is_template is True


async def test_add_trigger_template_with_loop_rejected(db_session: AsyncSession, chat, user):
    """Templates with for-loops should be rejected."""
    from app.bot.handlers.creation import add_trigger

    reply_content = {"text": "{% for i in range(100) %}spam{% endfor %}"}
    message = _make_message(chat.id, user.id, reply_content=reply_content)
    command = _make_command("-t evil_template")
    i18n = _make_i18n()

    await add_trigger(message, command, db_session, i18n, chat, user)

    stmt = select(Trigger).where(Trigger.chat_id == chat.id)
    result = await db_session.execute(stmt)
    assert result.scalars().first() is None


async def test_add_trigger_multiple_flags(db_session: AsyncSession, chat, user):
    from app.bot.handlers.creation import add_trigger

    reply_content = {"text": "Complex"}
    message = _make_message(chat.id, user.id, reply_content=reply_content)
    command = _make_command("-c -a complex_key")
    i18n = _make_i18n()

    await add_trigger(message, command, db_session, i18n, chat, user)

    stmt = select(Trigger).where(Trigger.chat_id == chat.id)
    result = await db_session.execute(stmt)
    trigger = result.scalars().first()

    assert trigger is not None
    assert trigger.is_case_sensitive is True
    assert trigger.access_level == AccessLevel.ADMINS


# ── Admin restrictions ──────────────────────────────────────────────────────


async def test_add_trigger_admins_only_chat_non_admin_rejected(
    db_session: AsyncSession, admins_only_chat, user
):
    from app.bot.handlers.creation import add_trigger

    reply_content = {"text": "Nope"}
    message = _make_message(admins_only_chat.id, user.id, reply_content=reply_content, is_admin=False)
    command = _make_command("blocked_key")
    i18n = _make_i18n()

    await add_trigger(message, command, db_session, i18n, admins_only_chat, user)

    message.answer.assert_awaited_once()
    assert message.answer.call_args.args[0] == "No rights"


async def test_add_trigger_admins_only_chat_admin_allowed(
    db_session: AsyncSession, admins_only_chat, user
):
    from app.bot.handlers.creation import add_trigger

    reply_content = {"text": "Admin content"}
    message = _make_message(admins_only_chat.id, user.id, reply_content=reply_content, is_admin=True)
    command = _make_command("admin_key")
    i18n = _make_i18n()

    await add_trigger(message, command, db_session, i18n, admins_only_chat, user)

    stmt = select(Trigger).where(Trigger.chat_id == admins_only_chat.id)
    result = await db_session.execute(stmt)
    assert result.scalars().first() is not None


# ── Skip moderation ─────────────────────────────────────────────────────────


async def test_add_trigger_trusted_chat_skips_moderation(
    db_session: AsyncSession, trusted_chat, user
):
    from app.bot.handlers.creation import add_trigger

    reply_content = {"text": "Trusted content"}
    message = _make_message(trusted_chat.id, user.id, reply_content=reply_content)
    command = _make_command("trusted_key")
    i18n = _make_i18n()

    await add_trigger(message, command, db_session, i18n, trusted_chat, user)

    stmt = select(Trigger).where(Trigger.chat_id == trusted_chat.id)
    result = await db_session.execute(stmt)
    trigger = result.scalars().first()

    assert trigger is not None
    assert trigger.moderation_status == ModerationStatus.SAFE


async def test_add_trigger_trusted_user_skips_moderation(
    db_session: AsyncSession, chat, trusted_user
):
    from app.bot.handlers.creation import add_trigger

    reply_content = {"text": "Trusted user content"}
    message = _make_message(chat.id, trusted_user.id, reply_content=reply_content)
    command = _make_command("trusted_user_key")
    i18n = _make_i18n()

    await add_trigger(message, command, db_session, i18n, chat, trusted_user)

    stmt = select(Trigger).where(Trigger.chat_id == chat.id)
    result = await db_session.execute(stmt)
    trigger = result.scalars().first()

    assert trigger is not None
    assert trigger.moderation_status == ModerationStatus.SAFE


async def test_add_trigger_moderator_user_skips_moderation(
    db_session: AsyncSession, chat, moderator_user
):
    from app.bot.handlers.creation import add_trigger

    reply_content = {"text": "Mod content"}
    message = _make_message(chat.id, moderator_user.id, reply_content=reply_content)
    command = _make_command("mod_key")
    i18n = _make_i18n()

    await add_trigger(message, command, db_session, i18n, chat, moderator_user)

    stmt = select(Trigger).where(Trigger.chat_id == chat.id)
    result = await db_session.execute(stmt)
    trigger = result.scalars().first()

    assert trigger is not None
    assert trigger.moderation_status == ModerationStatus.SAFE


async def test_add_trigger_untrusted_goes_to_pending(
    db_session: AsyncSession, chat, user
):
    from app.bot.handlers.creation import add_trigger

    reply_content = {"text": "Untrusted content"}
    message = _make_message(chat.id, user.id, reply_content=reply_content)
    command = _make_command("pending_key")
    i18n = _make_i18n()

    await add_trigger(message, command, db_session, i18n, chat, user)

    stmt = select(Trigger).where(Trigger.chat_id == chat.id)
    result = await db_session.execute(stmt)
    trigger = result.scalars().first()

    assert trigger is not None
    assert trigger.moderation_status == ModerationStatus.PENDING


# ── Multi-word key phrase ───────────────────────────────────────────────────


async def test_add_trigger_multi_word_key(db_session: AsyncSession, chat, user):
    from app.bot.handlers.creation import add_trigger

    reply_content = {"text": "Multi word response"}
    message = _make_message(chat.id, user.id, reply_content=reply_content)
    command = _make_command("hello world phrase")
    i18n = _make_i18n()

    await add_trigger(message, command, db_session, i18n, chat, user)

    stmt = select(Trigger).where(Trigger.chat_id == chat.id)
    result = await db_session.execute(stmt)
    trigger = result.scalars().first()

    assert trigger is not None
    assert trigger.key_phrase == "hello world phrase"
