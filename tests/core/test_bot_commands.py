"""Тесты регистрации команд бота: scoped-наборы (private/group) + is_ephemeral.

`status`/`warns`/`vars`/`auditlog` — персональные ответы (см. Task 6,
`ephemeral_answer`) и потому помечены `is_ephemeral=True` в group-scope наборе,
чтобы Telegram-клиент показывал их как эфемерные прямо из меню команд.
"""

from unittest.mock import AsyncMock, MagicMock

from aiogram.types import BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats
from app.bot.commands import GROUP_COMMANDS, PRIVATE_COMMANDS, set_bot_commands

EPHEMERAL_COMMANDS = {"status", "warns", "vars", "auditlog"}


def test_group_commands_mark_personal_replies_ephemeral():
    """status/warns/vars/auditlog в group-scope наборе помечены is_ephemeral=True."""
    ephemeral = {c.command for c in GROUP_COMMANDS if c.is_ephemeral}
    assert ephemeral == EPHEMERAL_COMMANDS


def test_non_ephemeral_group_commands_not_marked():
    """Остальные групповые команды НЕ помечены is_ephemeral."""
    assert all(not c.is_ephemeral for c in GROUP_COMMANDS if c.command not in EPHEMERAL_COMMANDS)


def test_private_commands_have_no_ephemeral_flags():
    """В личных сообщениях эфемерных команд нет — is_ephemeral нигде не выставлен."""
    assert all(not c.is_ephemeral for c in PRIVATE_COMMANDS)


def test_command_lists_have_no_duplicates():
    """Ни в одном scoped-наборе имя команды не повторяется дважды."""
    assert len(PRIVATE_COMMANDS) == len({c.command for c in PRIVATE_COMMANDS})
    assert len(GROUP_COMMANDS) == len({c.command for c in GROUP_COMMANDS})


def test_all_commands_have_descriptions():
    """У каждой команды непустое описание (Telegram отклоняет пустые)."""
    for cmd in [*PRIVATE_COMMANDS, *GROUP_COMMANDS]:
        assert cmd.description


async def test_set_bot_commands_registers_both_scopes():
    """set_bot_commands вызывает set_my_commands для all_private_chats и all_group_chats."""
    bot = MagicMock()
    bot.set_my_commands = AsyncMock()

    await set_bot_commands(bot)

    assert bot.set_my_commands.await_count == 2
    calls = bot.set_my_commands.await_args_list

    private_call = next(c for c in calls if isinstance(c.kwargs["scope"], BotCommandScopeAllPrivateChats))
    group_call = next(c for c in calls if isinstance(c.kwargs["scope"], BotCommandScopeAllGroupChats))

    assert private_call.kwargs["commands"] == PRIVATE_COMMANDS
    assert group_call.kwargs["commands"] == GROUP_COMMANDS
