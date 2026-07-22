"""Регистрация команд бота в меню Telegram-клиента (scoped-наборы).

Полный список собран из реальных `Command(...)`-фильтров в `app/bot/handlers/`
и разбит на два независимых scoped-набора:

- `PRIVATE_COMMANDS` (`BotCommandScopeAllPrivateChats`) — команды, работающие
  в личных сообщениях с ботом: wizard создания триггера, admin-панель,
  bot-level доверие/модераторство, отладка капчи.
- `GROUP_COMMANDS` (`BotCommandScopeAllGroupChats`) — команды, работающие
  внутри группового чата: модерация, настройки чата, репутация, переменные.

`/src` и `/wait` не привязаны к типу чата и присутствуют в обоих наборах.

`status`/`warns`/`vars`/`auditlog` отвечают персонально вызвавшему через
`ephemeral_answer` (Task 6) — помечены `is_ephemeral=True`, чтобы Telegram-клиент
показывал их как эфемерные уже из меню команд.

На момент введения (2026-07) в BotFather не было зарегистрировано ни одной
команды ни для одного из scope (снимок `getMyCommands` пуст везде), поэтому
списки собраны "с нуля" — ничего из предыдущей регистрации мержить не нужно.
"""

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats

PRIVATE_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="Start using the bot"),
    BotCommand(command="newtrigger", description="Create a new trigger via wizard"),
    BotCommand(command="cancel", description="Cancel the current wizard"),
    BotCommand(command="admin", description="Open the admin panel"),
    BotCommand(command="debug_captcha", description="Create a debug captcha session"),
    BotCommand(command="trust", description="Grant trusted status to a user"),
    BotCommand(command="untrust", description="Revoke trusted status from a user"),
    BotCommand(command="add_mod", description="Promote a bot moderator"),
    BotCommand(command="del_mod", description="Demote a bot moderator"),
    BotCommand(command="src", description="Show raw JSON of a message"),
    BotCommand(command="wait", description="Find the anime source of an image or video"),
]

GROUP_COMMANDS: list[BotCommand] = [
    BotCommand(command="newtrigger", description="Create a new trigger via wizard"),
    BotCommand(command="add", description="Add a trigger by replying to a message"),
    BotCommand(command="del", description="Delete a trigger by key"),
    BotCommand(command="triggers", description="List chat triggers"),
    BotCommand(command="settings", description="Open chat settings"),
    BotCommand(command="lang", description="Change chat language"),
    BotCommand(command="welcome", description="Manage welcome messages"),
    BotCommand(command="setvar", description="Set a chat variable"),
    BotCommand(command="delvar", description="Delete a chat variable"),
    BotCommand(command="vars", description="List chat variables", is_ephemeral=True),
    BotCommand(command="tag", description="Set a manual tag for a user"),
    BotCommand(command="deltag", description="Remove a manual tag from a user"),
    BotCommand(command="status", description="Show your reputation status", is_ephemeral=True),
    BotCommand(command="ban", description="Ban a user"),
    BotCommand(command="unban", description="Unban a user"),
    BotCommand(command="mute", description="Mute a user"),
    BotCommand(command="unmute", description="Unmute a user"),
    BotCommand(command="kick", description="Kick a user"),
    BotCommand(command="warn", description="Warn a user"),
    BotCommand(command="unwarn", description="Remove a warning from a user"),
    BotCommand(command="warns", description="List your warnings", is_ephemeral=True),
    BotCommand(command="auditlog", description="Show settings change history", is_ephemeral=True),
    BotCommand(command="src", description="Show raw JSON of a message"),
    BotCommand(command="wait", description="Find the anime source of an image or video"),
]


async def set_bot_commands(bot: Bot) -> None:
    """Зарегистрировать scoped-наборы команд в BotFather (private + group)."""
    await bot.set_my_commands(commands=PRIVATE_COMMANDS, scope=BotCommandScopeAllPrivateChats())
    await bot.set_my_commands(commands=GROUP_COMMANDS, scope=BotCommandScopeAllGroupChats())
