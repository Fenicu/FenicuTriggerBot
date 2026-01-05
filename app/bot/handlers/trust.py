from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from fluentogram import TranslatorRunner
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.user import User
from app.services.user_service import get_user, get_user_by_username

router = Router()


async def resolve_user(session: AsyncSession, arg: str) -> User | None:
    if arg.isdigit():
        return await get_user(session, int(arg))
    return await get_user_by_username(session, arg)


@router.message(Command("add_mod"))
async def add_mod(
    message: Message, command: CommandObject, session: AsyncSession, i18n: TranslatorRunner, user: User
) -> None:
    """Назначить модератора бота."""
    if message.from_user.id not in settings.BOT_ADMINS:
        return

    if not command.args:
        await message.answer(i18n.get("args-error"), parse_mode="HTML")
        return

    target_user = await resolve_user(session, command.args)
    if not target_user:
        await message.answer(i18n.get("user-not-found"), parse_mode="HTML")
        return

    target_user.is_bot_moderator = True
    target_user.is_trusted = True
    await session.commit()

    await message.answer(i18n.get("user-promoted-mod", user=target_user.username or target_user.id), parse_mode="HTML")


@router.message(Command("del_mod"))
async def del_mod(
    message: Message, command: CommandObject, session: AsyncSession, i18n: TranslatorRunner, user: User
) -> None:
    """Снять права модератора бота."""
    if message.from_user.id not in settings.BOT_ADMINS:
        return

    if not command.args:
        await message.answer(i18n.get("args-error"), parse_mode="HTML")
        return

    target_user = await resolve_user(session, command.args)
    if not target_user:
        await message.answer(i18n.get("user-not-found"), parse_mode="HTML")
        return

    target_user.is_bot_moderator = False
    await session.commit()

    await message.answer(i18n.get("user-demoted-mod", user=target_user.username or target_user.id), parse_mode="HTML")


@router.message(Command("trust"))
async def trust_user(
    message: Message, command: CommandObject, session: AsyncSession, i18n: TranslatorRunner, user: User
) -> None:
    """Назначить доверенного пользователя."""
    if not (message.from_user.id in settings.BOT_ADMINS or user.is_bot_moderator):
        return

    if not command.args:
        await message.answer(i18n.get("args-error"), parse_mode="HTML")
        return

    target_user = await resolve_user(session, command.args)
    if not target_user:
        await message.answer(i18n.get("user-not-found"), parse_mode="HTML")
        return

    target_user.is_trusted = True
    await session.commit()

    await message.answer(i18n.get("user-trusted", user=target_user.username or target_user.id), parse_mode="HTML")


@router.message(Command("untrust"))
async def untrust_user(
    message: Message, command: CommandObject, session: AsyncSession, i18n: TranslatorRunner, user: User
) -> None:
    """Снять статус доверенного пользователя."""
    if not (message.from_user.id in settings.BOT_ADMINS or user.is_bot_moderator):
        return

    if not command.args:
        await message.answer(i18n.get("args-error"), parse_mode="HTML")
        return

    target_user = await resolve_user(session, command.args)
    if not target_user:
        await message.answer(i18n.get("user-not-found"), parse_mode="HTML")
        return

    target_user.is_trusted = False
    await session.commit()

    await message.answer(i18n.get("user-untrusted", user=target_user.username or target_user.id), parse_mode="HTML")
