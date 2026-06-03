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
