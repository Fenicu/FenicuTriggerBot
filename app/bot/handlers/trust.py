from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from fluentogram import TranslatorRunner
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.user import User
from app.services.user_service import find_users_by_username, get_user

router = Router()


def _user_label(user: User) -> str:
    """Подпись пользователя для ответа: имя и id."""
    name = " ".join(part for part in (user.first_name, user.last_name) if part)
    name = name or user.username or ""
    if not name:
        return f"id {user.id}"
    return f"{escape(name)} (id {user.id})"


async def resolve_user(session: AsyncSession, arg: str) -> tuple[User | None, bool]:
    """Найти пользователя по id или username.

    Второй элемент — username неоднозначен (совпал у нескольких записей).
    """
    arg = arg.strip().lstrip("@")
    if arg.isdigit():
        return await get_user(session, int(arg)), False

    users = await find_users_by_username(session, arg)
    if len(users) > 1:
        return None, True

    return (users[0] if users else None), False


async def _resolve_or_answer(
    message: Message, command: CommandObject, session: AsyncSession, i18n: TranslatorRunner
) -> User | None:
    """Разобрать аргумент команды и ответить пользователю, если цель не найдена."""
    if not command.args:
        await message.answer(i18n.args.error(), parse_mode="HTML")
        return None

    target_user, ambiguous = await resolve_user(session, command.args)
    if ambiguous:
        await message.answer(i18n.user.ambiguous(), parse_mode="HTML")
        return None
    if not target_user:
        await message.answer(i18n.user.missing(), parse_mode="HTML")
        return None

    return target_user


@router.message(Command("add_mod"))
async def add_mod(
    message: Message, command: CommandObject, session: AsyncSession, i18n: TranslatorRunner, user: User
) -> None:
    """Назначить модератора бота."""
    if message.from_user.id not in settings.BOT_ADMINS:
        return

    target_user = await _resolve_or_answer(message, command, session, i18n)
    if not target_user:
        return

    target_user.is_bot_moderator = True
    target_user.is_trusted = True
    await session.commit()

    await message.answer(i18n.user.promoted.mod(user=_user_label(target_user)), parse_mode="HTML")


@router.message(Command("del_mod"))
async def del_mod(
    message: Message, command: CommandObject, session: AsyncSession, i18n: TranslatorRunner, user: User
) -> None:
    """Снять права модератора бота."""
    if message.from_user.id not in settings.BOT_ADMINS:
        return

    target_user = await _resolve_or_answer(message, command, session, i18n)
    if not target_user:
        return

    target_user.is_bot_moderator = False
    await session.commit()

    await message.answer(i18n.user.demoted.mod(user=_user_label(target_user)), parse_mode="HTML")


@router.message(Command("trust"))
async def trust_user(
    message: Message, command: CommandObject, session: AsyncSession, i18n: TranslatorRunner, user: User
) -> None:
    """Назначить доверенного пользователя."""
    if not (message.from_user.id in settings.BOT_ADMINS or user.is_bot_moderator):
        return

    target_user = await _resolve_or_answer(message, command, session, i18n)
    if not target_user:
        return

    target_user.is_trusted = True
    await session.commit()

    await message.answer(i18n.user.trusted(user=_user_label(target_user)), parse_mode="HTML")


@router.message(Command("untrust"))
async def untrust_user(
    message: Message, command: CommandObject, session: AsyncSession, i18n: TranslatorRunner, user: User
) -> None:
    """Снять статус доверенного пользователя."""
    if not (message.from_user.id in settings.BOT_ADMINS or user.is_bot_moderator):
        return

    target_user = await _resolve_or_answer(message, command, session, i18n)
    if not target_user:
        return

    target_user.is_trusted = False
    await session.commit()

    await message.answer(i18n.user.untrusted(user=_user_label(target_user)), parse_mode="HTML")
