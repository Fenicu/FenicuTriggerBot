from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from fluentogram import TranslatorRunner
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat_variable_service import del_var, get_vars, set_var, validate_key

router = Router()


@router.message(Command("setvar"))
async def set_var_command(
    message: Message, command: CommandObject, session: AsyncSession, i18n: TranslatorRunner
) -> None:
    """Установить переменную чата."""
    user_member = await message.chat.get_member(message.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await message.answer(i18n.get("error-no-rights"), parse_mode="HTML")
        return

    if not command.args:
        await message.answer(i18n.get("var-usage-set"), parse_mode="HTML")
        return

    parts = command.args.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer(i18n.get("var-usage-set"), parse_mode="HTML")
        return

    key, value = parts

    if not validate_key(key):
        await message.answer(i18n.get("var-invalid-key"), parse_mode="HTML")
        return

    await set_var(session, message.chat.id, key, value)
    await message.answer(i18n.get("var-set", key=key), parse_mode="HTML")


@router.message(Command("delvar"))
async def del_var_command(
    message: Message, command: CommandObject, session: AsyncSession, i18n: TranslatorRunner
) -> None:
    """Удалить переменную чата."""
    user_member = await message.chat.get_member(message.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await message.answer(i18n.get("error-no-rights"), parse_mode="HTML")
        return

    if not command.args:
        await message.answer(i18n.get("var-usage-del"), parse_mode="HTML")
        return

    key = command.args.strip()

    deleted = await del_var(session, message.chat.id, key)
    if deleted:
        await message.answer(i18n.get("var-deleted", key=key), parse_mode="HTML")
    else:
        await message.answer(i18n.get("var-not-found", key=key), parse_mode="HTML")


@router.message(Command("vars"))
async def list_vars_command(message: Message, session: AsyncSession, i18n: TranslatorRunner) -> None:
    """Показать список переменных чата."""
    user_member = await message.chat.get_member(message.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await message.answer(i18n.get("error-no-rights"), parse_mode="HTML")
        return

    variables = await get_vars(session, message.chat.id)
    if not variables:
        await message.answer(i18n.get("var-list-empty"), parse_mode="HTML")
        return

    text = [i18n.get("var-list-header")]
    for key, value in variables.items():
        text.append(f"<code>{key}</code>: {value}")

    await message.answer("\n".join(text), parse_mode="HTML")
