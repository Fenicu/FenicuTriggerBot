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


# ─── /newtrigger в ЛС — lobby chat-picker ────────────────────────────────────


@pytest.mark.asyncio
async def test_newtrigger_in_dm_enters_choosing_chat_state(db_session):
    """В ЛС /newtrigger → state=choosing_chat, рендер списка чатов."""
    from app.bot.handlers.creation_private import newtrigger_dm_entry, NewTriggerStates
    from tests.factories import create_chat, create_user_chat, create_user

    user = await create_user(db_session)
    chat = await create_chat(db_session, admins_only_add=False)
    await create_user_chat(db_session, user_id=user.id, chat_id=chat.id, is_admin=False)

    msg = _dm_message(user_id=user.id)
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()

    await newtrigger_dm_entry(msg, state=state, session=db_session, i18n=_i18n_runner())

    state.set_state.assert_awaited_with(NewTriggerStates.choosing_chat)
    msg.answer.assert_awaited()


@pytest.mark.asyncio
async def test_newtrigger_in_dm_lists_only_eligible_chats(db_session):
    """Чат с admins_only_add=True должен быть в списке только если user — админ."""
    from app.bot.handlers.creation_private import _list_eligible_chats
    from tests.factories import create_chat, create_user_chat, create_user

    user = await create_user(db_session)
    chat_ok = await create_chat(db_session, admins_only_add=False)
    chat_admin_only = await create_chat(db_session, admins_only_add=True)
    chat_admin_only_user_admin = await create_chat(db_session, admins_only_add=True)

    await create_user_chat(db_session, user_id=user.id, chat_id=chat_ok.id, is_admin=False)
    await create_user_chat(db_session, user_id=user.id, chat_id=chat_admin_only.id, is_admin=False)
    await create_user_chat(
        db_session, user_id=user.id, chat_id=chat_admin_only_user_admin.id, is_admin=True
    )

    chats, total = await _list_eligible_chats(db_session, user_id=user.id, page=0)
    ids = {c.id for c in chats}
    assert chat_ok.id in ids
    assert chat_admin_only_user_admin.id in ids
    assert chat_admin_only.id not in ids
    assert total == 2


@pytest.mark.asyncio
async def test_newtrigger_in_dm_shows_empty_when_no_eligible_chats(db_session):
    from app.bot.handlers.creation_private import newtrigger_dm_entry
    from tests.factories import create_user

    user = await create_user(db_session)
    msg = _dm_message(user_id=user.id)
    state = AsyncMock()
    state.get_state = AsyncMock(return_value=None)
    state.set_state = AsyncMock()

    await newtrigger_dm_entry(msg, state=state, session=db_session, i18n=_i18n_runner())

    state.set_state.assert_not_called()
    msg.answer.assert_awaited()


# ─── Callback'и chat picker'а ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_picker_callback_sets_chat_id_and_advances(db_session):
    from app.bot.handlers.creation_private import handle_chat_picked, NewTriggerStates
    from tests.factories import create_chat, create_user

    user = await create_user(db_session)
    chat = await create_chat(db_session, admins_only_add=False)

    callback = MagicMock()
    callback.from_user = MagicMock(id=user.id)
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    bot = _bot()
    bot.get_chat_member = AsyncMock(return_value=MagicMock(status="member"))

    cb_data = MagicMock(action="chat", value=str(chat.id))
    await handle_chat_picked(callback, callback_data=cb_data, state=state, session=db_session, bot=bot, i18n=_i18n_runner())

    state.set_state.assert_awaited_with(NewTriggerStates.awaiting_content)
    state.update_data.assert_awaited()


@pytest.mark.asyncio
async def test_chat_picker_denies_when_live_check_fails(db_session):
    from app.bot.handlers.creation_private import handle_chat_picked
    from tests.factories import create_chat, create_user

    user = await create_user(db_session)
    chat = await create_chat(db_session, admins_only_add=True)

    callback = MagicMock()
    callback.from_user = MagicMock(id=user.id)
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock()
    state.set_state = AsyncMock()
    state.clear = AsyncMock()
    bot = _bot()
    bot.get_chat_member = AsyncMock(return_value=MagicMock(status="member"))  # не админ

    cb_data = MagicMock(action="chat", value=str(chat.id))
    await handle_chat_picked(callback, callback_data=cb_data, state=state, session=db_session, bot=bot, i18n=_i18n_runner())

    state.set_state.assert_not_called()
    state.clear.assert_awaited()


@pytest.mark.asyncio
async def test_chat_picker_pagination_callback_re_renders(db_session):
    from app.bot.handlers.creation_private import handle_chat_picker_page
    from tests.factories import create_chat, create_user, create_user_chat

    user = await create_user(db_session)
    for _ in range(10):
        c = await create_chat(db_session, admins_only_add=False)
        await create_user_chat(db_session, user_id=user.id, chat_id=c.id, is_admin=False)

    callback = MagicMock()
    callback.from_user = MagicMock(id=user.id)
    callback.message = MagicMock()
    callback.message.edit_reply_markup = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock()
    state.update_data = AsyncMock()

    cb_data = MagicMock(action="page", value="1")
    await handle_chat_picker_page(callback, callback_data=cb_data, state=state, session=db_session, i18n=_i18n_runner())

    callback.message.edit_reply_markup.assert_awaited()
    state.update_data.assert_awaited_with(page=1)


# ─── awaiting_content handler ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_content_text_advances_to_awaiting_key():
    from app.bot.handlers.creation_private import handle_content_received, NewTriggerStates

    msg = _dm_message(text="hello!")
    # Реализация вызывает model_dump_json (как в существующем /add)
    msg.model_dump_json = MagicMock(return_value='{"text": "hello!", "message_id": 1}')
    msg.caption = None
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"chat_id": -100, "source": "lobby"})
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()

    await handle_content_received(msg, state=state, i18n=_i18n_runner())

    state.set_state.assert_awaited_with(NewTriggerStates.awaiting_key)
    state.update_data.assert_awaited()
    args = state.update_data.await_args.kwargs
    assert "content" in args
    assert args["content"]["text"] == "hello!"
    msg.answer.assert_awaited()


@pytest.mark.asyncio
async def test_content_command_shows_soft_confirm():
    from app.bot.handlers.creation_private import handle_content_received

    msg = _dm_message(text="/foo")
    msg.caption = None
    msg.model_dump_json = MagicMock(return_value='{"text": "/foo"}')
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"chat_id": -100, "source": "lobby"})
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()

    await handle_content_received(msg, state=state, i18n=_i18n_runner())

    state.set_state.assert_not_called()
    args = state.update_data.await_args.kwargs
    assert "pending_content" in args
    msg.answer.assert_awaited()


@pytest.mark.asyncio
async def test_content_command_with_args_shows_soft_confirm():
    """/cmd arg1 arg2 — тоже команда."""
    from app.bot.handlers.creation_private import handle_content_received

    msg = _dm_message(text="/test some args")
    msg.caption = None
    msg.model_dump_json = MagicMock(return_value='{"text": "/test some args"}')
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"chat_id": -100, "source": "lobby"})
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()

    await handle_content_received(msg, state=state, i18n=_i18n_runner())

    state.set_state.assert_not_called()


@pytest.mark.asyncio
async def test_confirm_command_content_advances():
    from app.bot.handlers.creation_private import handle_confirm_command_content, NewTriggerStates

    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"pending_content": {"text": "/foo"}})
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()

    await handle_confirm_command_content(callback, state=state, i18n=_i18n_runner())

    state.set_state.assert_awaited_with(NewTriggerStates.awaiting_key)
    # Проверим что content скопирован, pending_content обнулён
    update_calls = state.update_data.await_args_list
    final_args = update_calls[-1].kwargs
    assert final_args.get("content") == {"text": "/foo"}
    assert final_args.get("pending_content") is None


@pytest.mark.asyncio
async def test_reject_command_content_clears_pending():
    from app.bot.handlers.creation_private import handle_reject_command_content

    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"chat_id": -100, "source": "lobby"})
    state.update_data = AsyncMock()

    await handle_reject_command_content(callback, state=state, i18n=_i18n_runner())

    update_calls = state.update_data.await_args_list
    final_args = update_calls[-1].kwargs
    assert final_args.get("pending_content") is None


@pytest.mark.asyncio
async def test_back_to_chat_callback_returns_to_choosing_chat_for_lobby(db_session):
    from app.bot.handlers.creation_private import handle_back_to_chat, NewTriggerStates
    from tests.factories import create_user, create_chat, create_user_chat

    user = await create_user(db_session)
    c = await create_chat(db_session, admins_only_add=False)
    await create_user_chat(db_session, user_id=user.id, chat_id=c.id, is_admin=False)

    callback = MagicMock()
    callback.from_user = MagicMock(id=user.id)
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"source": "lobby"})
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()

    await handle_back_to_chat(callback, state=state, session=db_session, i18n=_i18n_runner())

    state.set_state.assert_awaited_with(NewTriggerStates.choosing_chat)
    callback.message.edit_text.assert_awaited()


@pytest.mark.asyncio
async def test_back_to_chat_callback_no_op_for_deeplink_source():
    from app.bot.handlers.creation_private import handle_back_to_chat

    callback = MagicMock()
    callback.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"source": "deeplink"})
    state.set_state = AsyncMock()
    session = MagicMock()

    await handle_back_to_chat(callback, state=state, session=session, i18n=_i18n_runner())

    state.set_state.assert_not_called()
    callback.answer.assert_awaited()


# ─── awaiting_key handler ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_key_text_advances_to_configuring_flags():
    from app.bot.handlers.creation_private import handle_key_received, NewTriggerStates

    msg = _dm_message(text="привет")
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"chat_id": -100, "content": {"text": "x"}, "key_phrase": "привет"})
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()

    with patch("app.bot.handlers.creation_private._render_flags_message", new=AsyncMock()):
        await handle_key_received(msg, state=state, i18n=_i18n_runner())

    state.set_state.assert_awaited_with(NewTriggerStates.configuring_flags)
    args = state.update_data.await_args_list[0].kwargs
    assert args.get("key_phrase") == "привет"


@pytest.mark.asyncio
async def test_key_empty_keeps_state():
    from app.bot.handlers.creation_private import handle_key_received

    msg = _dm_message(text="   ")  # whitespace only
    msg.answer = AsyncMock()
    state = AsyncMock()
    state.set_state = AsyncMock()

    await handle_key_received(msg, state=state, i18n=_i18n_runner())

    state.set_state.assert_not_called()
    msg.answer.assert_awaited()


@pytest.mark.asyncio
async def test_key_too_long_keeps_state():
    from app.bot.handlers.creation_private import handle_key_received, KEY_PHRASE_LIMIT

    msg = _dm_message(text="x" * (KEY_PHRASE_LIMIT + 1))
    state = AsyncMock()
    state.set_state = AsyncMock()

    await handle_key_received(msg, state=state, i18n=_i18n_runner())

    state.set_state.assert_not_called()
    msg.answer.assert_awaited()


# ─── configuring_flags callback'и ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_flag_match_radio_clears_other_options():
    from app.bot.handlers.creation_private import handle_flag_toggle

    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "key_phrase": "x",
        "match_type": "exact",
        "is_case_sensitive": False,
        "access_level": "all",
        "is_template": False,
    })
    state.update_data = AsyncMock()

    cb_data = MagicMock(action="flag", value="match|regexp")
    with patch("app.bot.handlers.creation_private._render_flags_message", new=AsyncMock()):
        await handle_flag_toggle(callback, callback_data=cb_data, state=state, i18n=_i18n_runner())

    state.update_data.assert_awaited_with(match_type="regexp")


@pytest.mark.asyncio
async def test_flag_case_toggle_flips_value():
    from app.bot.handlers.creation_private import handle_flag_toggle

    callback = MagicMock()
    callback.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "key_phrase": "x",
        "match_type": "exact",
        "is_case_sensitive": False,
        "access_level": "all",
        "is_template": False,
    })
    state.update_data = AsyncMock()

    cb_data = MagicMock(action="flag", value="case")
    with patch("app.bot.handlers.creation_private._render_flags_message", new=AsyncMock()):
        await handle_flag_toggle(callback, callback_data=cb_data, state=state, i18n=_i18n_runner())

    state.update_data.assert_awaited_with(is_case_sensitive=True)


@pytest.mark.asyncio
async def test_flag_template_toggle_flips():
    from app.bot.handlers.creation_private import handle_flag_toggle

    callback = MagicMock()
    callback.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "key_phrase": "x",
        "match_type": "exact",
        "is_case_sensitive": False,
        "access_level": "all",
        "is_template": True,
    })
    state.update_data = AsyncMock()

    cb_data = MagicMock(action="flag", value="template")
    with patch("app.bot.handlers.creation_private._render_flags_message", new=AsyncMock()):
        await handle_flag_toggle(callback, callback_data=cb_data, state=state, i18n=_i18n_runner())

    state.update_data.assert_awaited_with(is_template=False)


@pytest.mark.asyncio
async def test_flag_access_radio():
    from app.bot.handlers.creation_private import handle_flag_toggle

    callback = MagicMock()
    callback.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "key_phrase": "x",
        "match_type": "exact",
        "is_case_sensitive": False,
        "access_level": "all",
        "is_template": False,
    })
    state.update_data = AsyncMock()

    cb_data = MagicMock(action="flag", value="access|owner")
    with patch("app.bot.handlers.creation_private._render_flags_message", new=AsyncMock()):
        await handle_flag_toggle(callback, callback_data=cb_data, state=state, i18n=_i18n_runner())

    state.update_data.assert_awaited_with(access_level="owner")


# ─── handle_next и handle_back_to_key ────────────────────────────────────────


@pytest.mark.asyncio
async def test_next_advances_to_confirming_on_valid():
    from app.bot.handlers.creation_private import handle_next, NewTriggerStates

    callback = MagicMock()
    callback.from_user = MagicMock(id=42)
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "chat_id": -100,
        "content": {"text": "ok"},
        "key_phrase": "привет",
        "match_type": "exact",
        "is_case_sensitive": False,
        "access_level": "all",
        "is_template": False,
    })
    state.set_state = AsyncMock()
    session = MagicMock()
    bot = _bot()

    with patch("app.bot.handlers.creation_private._render_preview", new=AsyncMock()) as rp:
        await handle_next(callback, state=state, session=session, bot=bot, i18n=_i18n_runner())

    state.set_state.assert_awaited_with(NewTriggerStates.confirming)
    rp.assert_awaited()


@pytest.mark.asyncio
async def test_next_validates_regex_and_shows_alert_on_invalid():
    from app.bot.handlers.creation_private import handle_next

    callback = MagicMock()
    callback.from_user = MagicMock(id=42)
    callback.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "chat_id": -100,
        "content": {"text": "ok"},
        "key_phrase": "(bad",  # незакрытая скобка
        "match_type": "regexp",  # ВНИМАНИЕ: regexp, не regex
        "is_case_sensitive": False,
        "access_level": "all",
        "is_template": False,
    })
    state.set_state = AsyncMock()
    session = MagicMock()
    bot = _bot()

    await handle_next(callback, state=state, session=session, bot=bot, i18n=_i18n_runner())

    state.set_state.assert_not_called()
    callback.answer.assert_awaited()


@pytest.mark.asyncio
async def test_back_to_key_returns_to_awaiting_key():
    from app.bot.handlers.creation_private import handle_back_to_key, NewTriggerStates

    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock()
    state.set_state = AsyncMock()

    await handle_back_to_key(callback, state=state, i18n=_i18n_runner())

    state.set_state.assert_awaited_with(NewTriggerStates.awaiting_key)


@pytest.mark.asyncio
async def test_render_preview_sends_send_copy_and_summary(db_session):
    from app.bot.handlers.creation_private import _render_preview
    from tests.factories import create_chat, create_user

    user = await create_user(db_session)
    chat = await create_chat(db_session, admins_only_add=False, title="My Chat")

    callback = MagicMock()
    callback.from_user = MagicMock(id=user.id, username="alice", full_name="Alice")
    callback.message = MagicMock()
    callback.message.chat = MagicMock(id=user.id)
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={
        "chat_id": chat.id,
        "content": {"text": "Hello", "message_id": 1, "date": 0,
                    "chat": {"id": -100, "type": "supergroup", "title": "X"}},
        "key_phrase": "привет",
        "match_type": "exact",
        "is_case_sensitive": False,
        "access_level": "all",
        "is_template": False,
    })
    bot = _bot()
    bot.send_message = AsyncMock()

    with patch("app.bot.handlers.creation_private.AiogramMessage") as MockMsg:
        saved = MagicMock()
        saved.send_copy = AsyncMock()
        MockMsg.model_validate.return_value = saved
        await _render_preview(callback, state=state, session=db_session, bot=bot, i18n=_i18n_runner())
        saved.send_copy.assert_awaited()

    # Управляющее сообщение шлётся отдельным bot.send_message
    bot.send_message.assert_awaited()


@pytest.mark.asyncio
async def test_save_creates_trigger_when_lock_acquired_and_perms_ok(db_session):
    from app.bot.handlers.creation_private import _save_via_wizard
    from tests.factories import create_chat, create_user

    user = await create_user(db_session)
    chat = await create_chat(db_session, admins_only_add=False, is_active=True)

    bot = _bot()
    bot.get_chat_member = AsyncMock(return_value=MagicMock(status="member"))

    with patch("app.bot.handlers.creation_private.valkey") as vk, \
         patch("app.bot.handlers.creation_private.trigger_service.create_trigger", new=AsyncMock(return_value=MagicMock(id=1))) as ct:
        vk.set = AsyncMock(return_value=True)  # SETNX success
        vk.eval = AsyncMock()
        vk.delete = AsyncMock()
        result = await _save_via_wizard(
            user_id=user.id,
            chat_id=chat.id,
            content={"text": "x"},
            key_phrase="hi",
            match_type="exact",
            is_case_sensitive=False,
            access_level="all",
            is_template=False,
            session=db_session,
            bot=bot,
        )
        assert result.status == "ok"
        ct.assert_awaited()


@pytest.mark.asyncio
async def test_save_returns_lock_busy_when_setnx_fails(db_session):
    from app.bot.handlers.creation_private import _save_via_wizard
    from tests.factories import create_chat, create_user

    user = await create_user(db_session)
    chat = await create_chat(db_session, admins_only_add=False)

    bot = _bot()

    with patch("app.bot.handlers.creation_private.valkey") as vk, \
         patch("app.bot.handlers.creation_private.trigger_service.create_trigger", new=AsyncMock()) as ct:
        vk.set = AsyncMock(return_value=None)  # SETNX failed
        result = await _save_via_wizard(
            user_id=user.id, chat_id=chat.id, content={"text": "x"}, key_phrase="hi",
            match_type="exact", is_case_sensitive=False, access_level="all",
            is_template=False, session=db_session, bot=bot,
        )
        assert result.status == "lock_busy"
        ct.assert_not_called()


@pytest.mark.asyncio
async def test_save_returns_db_error_when_create_trigger_raises(db_session):
    from app.bot.handlers.creation_private import _save_via_wizard
    from tests.factories import create_chat, create_user

    user = await create_user(db_session)
    chat = await create_chat(db_session, admins_only_add=False)

    bot = _bot()
    bot.get_chat_member = AsyncMock(return_value=MagicMock(status="member"))

    with patch("app.bot.handlers.creation_private.valkey") as vk, \
         patch(
             "app.bot.handlers.creation_private.trigger_service.create_trigger",
             new=AsyncMock(side_effect=RuntimeError("constraint violation")),
         ):
        vk.set = AsyncMock(return_value=True)
        vk.eval = AsyncMock()
        result = await _save_via_wizard(
            user_id=user.id, chat_id=chat.id, content={"text": "x"}, key_phrase="hi",
            match_type="exact", is_case_sensitive=False, access_level="all",
            is_template=False, session=db_session, bot=bot,
        )
        assert result.status == "db_error"
        assert "constraint" in (result.error or "")
        vk.eval.assert_awaited()


@pytest.mark.asyncio
async def test_save_release_uses_lua_compare_and_delete(db_session):
    """В finally вместо безусловного delete используется eval с проверкой owner-token."""
    from app.bot.handlers.creation_private import _save_via_wizard
    from tests.factories import create_chat, create_user

    user = await create_user(db_session)
    chat = await create_chat(db_session, admins_only_add=False)

    bot = _bot()
    bot.get_chat_member = AsyncMock(return_value=MagicMock(status="member"))

    with patch("app.bot.handlers.creation_private.valkey") as vk, \
         patch(
             "app.bot.handlers.creation_private.trigger_service.create_trigger",
             new=AsyncMock(return_value=MagicMock(id=1)),
         ):
        vk.set = AsyncMock(return_value=True)
        vk.eval = AsyncMock()
        await _save_via_wizard(
            user_id=user.id, chat_id=chat.id, content={"text": "x"}, key_phrase="hi",
            match_type="exact", is_case_sensitive=False, access_level="all",
            is_template=False, session=db_session, bot=bot,
        )
        vk.eval.assert_awaited()
        # Безусловного delete на ключ не должно быть
        assert not vk.delete.await_args_list


@pytest.mark.asyncio
async def test_save_aborts_when_permission_lost(db_session):
    from app.bot.handlers.creation_private import _save_via_wizard
    from tests.factories import create_chat, create_user

    user = await create_user(db_session)
    chat = await create_chat(db_session, admins_only_add=True)  # требует админа

    bot = _bot()
    bot.get_chat_member = AsyncMock(return_value=MagicMock(status="member"))  # не админ

    with patch("app.bot.handlers.creation_private.valkey") as vk, \
         patch("app.bot.handlers.creation_private.trigger_service.create_trigger", new=AsyncMock()) as ct:
        vk.set = AsyncMock(return_value=True)
        vk.eval = AsyncMock()
        result = await _save_via_wizard(
            user_id=user.id, chat_id=chat.id, content={"text": "x"}, key_phrase="hi",
            match_type="exact", is_case_sensitive=False, access_level="all",
            is_template=False, session=db_session, bot=bot,
        )
        assert result.status == "permission_lost"
        ct.assert_not_called()
