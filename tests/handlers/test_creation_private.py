"""Handler-тесты wizard'а в creation_private.py."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── FakeI18n: dotted-path access без MagicMock magic-attr hacks ──────────────


class _FakeI18nNode:
    """Узел dotted-path для FakeI18n.

    `i18n.new.trigger.btn.cancel()` → возвращает строку "new.trigger.btn.cancel".
    Не использует `__setattr__` на MagicMock (это запрещено для magic methods).
    """
    def __init__(self, path: str = "") -> None:
        object.__setattr__(self, "_path", path)

    def __getattr__(self, name: str) -> "_FakeI18nNode":
        new_path = f"{self._path}.{name}" if self._path else name
        return _FakeI18nNode(new_path)

    def __call__(self, **kwargs) -> str:
        if kwargs:
            args_str = ",".join(f"{k}={v}" for k, v in kwargs.items())
            return f"{self._path}({args_str})"
        return self._path


def _i18n_runner() -> _FakeI18nNode:
    """Fake TranslatorRunner с dotted-path interface."""
    return _FakeI18nNode()


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _bot():
    bot = MagicMock()
    bot.id = 1
    bot.get_me = AsyncMock(return_value=MagicMock(username="testbot"))
    bot.send_message = AsyncMock()
    return bot


def _dm_message(user_id=42, text="/start newtrigger_-100123"):
    msg = MagicMock()
    msg.chat = MagicMock(id=user_id, type="private")
    msg.from_user = MagicMock(id=user_id, username="alice", full_name="Alice")
    msg.text = text
    msg.bot = _bot()
    msg.answer = AsyncMock()
    return msg


def _group_message(chat_id=-100123, user_id=42, text="/newtrigger"):
    msg = MagicMock()
    msg.chat = MagicMock(id=chat_id, type="supergroup", title="Test Chat")
    msg.from_user = MagicMock(id=user_id, username="alice", full_name="Alice")
    msg.text = text
    msg.bot = _bot()
    msg.answer = AsyncMock()
    member = MagicMock(status="administrator")
    msg.chat.get_member = AsyncMock(return_value=member)
    return msg


# ─── /newtrigger в группе ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_group_entry_shows_deep_link_button_for_admin():
    from app.bot.handlers.creation_private import newtrigger_group_entry

    msg = _group_message()
    db_chat = MagicMock(admins_only_add=True, is_active=True)
    i18n = _i18n_runner()

    await newtrigger_group_entry(msg, db_chat=db_chat, i18n=i18n)

    msg.answer.assert_awaited()
    call = msg.answer.await_args
    reply_markup = call.kwargs.get("reply_markup") or call.args[1] if len(call.args) > 1 else call.kwargs.get("reply_markup")
    assert reply_markup is not None
    button = reply_markup.inline_keyboard[0][0]
    assert "newtrigger_-100123" in button.url
    assert "testbot" in button.url


@pytest.mark.asyncio
async def test_group_entry_shows_for_member_when_admins_only_add_false():
    from app.bot.handlers.creation_private import newtrigger_group_entry

    msg = _group_message()
    msg.chat.get_member = AsyncMock(return_value=MagicMock(status="member"))
    db_chat = MagicMock(admins_only_add=False, is_active=True)
    i18n = _i18n_runner()

    await newtrigger_group_entry(msg, db_chat=db_chat, i18n=i18n)
    msg.answer.assert_awaited()


@pytest.mark.asyncio
async def test_group_entry_denies_for_member_when_admins_only_add_true():
    from app.bot.handlers.creation_private import newtrigger_group_entry

    msg = _group_message()
    msg.chat.get_member = AsyncMock(return_value=MagicMock(status="member"))
    db_chat = MagicMock(admins_only_add=True, is_active=True)
    i18n = _i18n_runner()

    await newtrigger_group_entry(msg, db_chat=db_chat, i18n=i18n)

    msg.answer.assert_awaited()
    call = msg.answer.await_args
    reply_markup = call.kwargs.get("reply_markup")
    assert reply_markup is None


# ─── start_from_deep_link ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deep_link_starts_wizard_in_awaiting_content():
    from app.bot.handlers.creation_private import (
        NewTriggerStates,
        start_from_deep_link,
    )

    msg = _dm_message()
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    session = MagicMock()
    db_chat = MagicMock(id=-100123, is_active=True, admins_only_add=True, title="T")
    session.get = AsyncMock(return_value=db_chat)
    bot = msg.bot
    bot.get_chat_member = AsyncMock(return_value=MagicMock(status="administrator"))

    await start_from_deep_link(msg, chat_id=-100123, state=state, session=session, bot=bot, i18n=_i18n_runner())

    state.set_state.assert_awaited_with(NewTriggerStates.awaiting_content)
    state.update_data.assert_awaited()
    kwargs = state.update_data.await_args.kwargs
    assert kwargs.get("chat_id") == -100123
    assert kwargs.get("source") == "deeplink"


@pytest.mark.asyncio
async def test_deep_link_denies_when_admins_only_add_and_not_admin():
    from app.bot.handlers.creation_private import start_from_deep_link

    msg = _dm_message()
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    session = MagicMock()
    db_chat = MagicMock(id=-100123, is_active=True, admins_only_add=True, title="T")
    session.get = AsyncMock(return_value=db_chat)
    bot = msg.bot
    bot.get_chat_member = AsyncMock(return_value=MagicMock(status="member"))

    await start_from_deep_link(msg, chat_id=-100123, state=state, session=session, bot=bot, i18n=_i18n_runner())

    state.set_state.assert_not_called()
    msg.answer.assert_awaited()


@pytest.mark.asyncio
async def test_deep_link_denies_when_chat_not_found_in_db():
    from app.bot.handlers.creation_private import start_from_deep_link

    msg = _dm_message()
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    session = MagicMock()
    session.get = AsyncMock(return_value=None)

    await start_from_deep_link(msg, chat_id=-100123, state=state, session=session, bot=msg.bot, i18n=_i18n_runner())

    state.set_state.assert_not_called()
    msg.answer.assert_awaited()


@pytest.mark.asyncio
async def test_deep_link_denies_when_user_left():
    from app.bot.handlers.creation_private import start_from_deep_link

    msg = _dm_message()
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    session = MagicMock()
    db_chat = MagicMock(id=-100123, is_active=True, admins_only_add=False, title="T")
    session.get = AsyncMock(return_value=db_chat)
    bot = msg.bot
    bot.get_chat_member = AsyncMock(return_value=MagicMock(status="left"))

    await start_from_deep_link(msg, chat_id=-100123, state=state, session=session, bot=bot, i18n=_i18n_runner())

    state.set_state.assert_not_called()


@pytest.mark.asyncio
async def test_deep_link_marks_chat_inactive_on_forbidden():
    from aiogram.exceptions import TelegramForbiddenError
    from app.bot.handlers.creation_private import start_from_deep_link

    msg = _dm_message()
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    session = MagicMock()
    db_chat = MagicMock(id=-100123, is_active=True, admins_only_add=True, title="T")
    session.get = AsyncMock(return_value=db_chat)
    session.commit = AsyncMock()
    bot = msg.bot
    bot.get_chat_member = AsyncMock(
        side_effect=TelegramForbiddenError(method=MagicMock(), message="Forbidden")
    )

    await start_from_deep_link(msg, chat_id=-100123, state=state, session=session, bot=bot, i18n=_i18n_runner())

    assert db_chat.is_active is False
    session.commit.assert_awaited()
    state.set_state.assert_not_called()


@pytest.mark.asyncio
async def test_start_handler_delegates_newtrigger_deep_link():
    """/start newtrigger_-100 должен делегировать в start_from_deep_link."""
    with patch("app.bot.handlers.common.start_from_deep_link", new=AsyncMock()) as sfdl:
        from app.bot.handlers.common import start_command

        msg = _dm_message(text="/start newtrigger_-100123")
        state = AsyncMock()
        session = MagicMock()
        i18n = _i18n_runner()
        await start_command(msg, i18n=i18n, session=session, state=state)
        sfdl.assert_awaited_once()
        call = sfdl.await_args
        assert call.kwargs.get("chat_id") == -100123 or (
            len(call.args) > 1 and call.args[1] == -100123
        )


@pytest.mark.asyncio
async def test_start_handler_does_not_match_invalid_newtrigger_args():
    """/start newtrigger_abc должен падать в default-ветку (welcome message)."""
    with patch("app.bot.handlers.common.start_from_deep_link", new=AsyncMock()) as sfdl:
        from app.bot.handlers.common import start_command

        msg = _dm_message(text="/start newtrigger_abc")
        state = AsyncMock()
        session = MagicMock()
        i18n = _i18n_runner()
        await start_command(msg, i18n=i18n, session=session, state=state)
        sfdl.assert_not_called()
        msg.answer.assert_awaited()


# ─── Conflict-guard тесты ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_deep_link_shows_conflict_when_state_active():
    """При уже активном state'е — диалог конфликта, без сброса."""
    from app.bot.handlers.creation_private import start_from_deep_link, NewTriggerStates

    msg = _dm_message()
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=NewTriggerStates.awaiting_content.state)
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    session = MagicMock()
    db_chat = MagicMock(id=-100123, is_active=True, admins_only_add=False, title="T")
    session.get = AsyncMock(return_value=db_chat)
    bot = msg.bot
    bot.get_chat_member = AsyncMock(return_value=MagicMock(status="member"))

    await start_from_deep_link(msg, chat_id=-100123, state=state, session=session, bot=bot, i18n=_i18n_runner())

    state.set_state.assert_not_called()
    msg.answer.assert_awaited()
    call = msg.answer.await_args
    reply_markup = call.kwargs.get("reply_markup")
    assert reply_markup is not None
    buttons = reply_markup.inline_keyboard[0]
    assert len(buttons) == 2


@pytest.mark.asyncio
async def test_conflict_restart_callback_clears_and_starts_for_deep_link():
    from app.bot.handlers.creation_private import handle_conflict_restart, NewTriggerStates

    callback = MagicMock()
    callback.from_user = MagicMock(id=42)
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock()
    state.clear = AsyncMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    session = MagicMock()
    db_chat = MagicMock(id=-100123, is_active=True, admins_only_add=False, title="T")
    session.get = AsyncMock(return_value=db_chat)
    bot = _bot()
    bot.get_chat_member = AsyncMock(return_value=MagicMock(status="administrator"))

    cb_data = MagicMock(action="restart", value="-100123")
    await handle_conflict_restart(callback, callback_data=cb_data, state=state, session=session, bot=bot, i18n=_i18n_runner())

    state.clear.assert_awaited()
    state.set_state.assert_awaited_with(NewTriggerStates.awaiting_content)


@pytest.mark.asyncio
async def test_conflict_keep_callback_keeps_state():
    from app.bot.handlers.creation_private import handle_conflict_keep

    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock()
    state.clear = AsyncMock()
    state.set_state = AsyncMock()

    await handle_conflict_keep(callback, state=state, i18n=_i18n_runner())

    state.clear.assert_not_called()
    state.set_state.assert_not_called()
    callback.message.edit_text.assert_awaited()
