import html
import json
import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from fluentogram import TranslatorRunner
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.chat import Chat
from app.db.models.trigger import AccessLevel, MatchType
from app.db.models.user import User
from app.services.template_service import validate_template
from app.services.trigger_service import create_trigger

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("add"))
async def add_trigger(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    i18n: TranslatorRunner,
    db_chat: Chat,
    user: User,
) -> None:
    """Добавление нового триггера."""
    if not message.reply_to_message:
        await message.answer(i18n.get("trigger-add-error"), parse_mode="HTML")
        return

    args = command.args
    if not args:
        await message.answer(i18n.get("add-usage"), parse_mode="HTML")
        return

    parts = args.split()
    flags = []
    key_parts = []

    valid_flags = {
        "-c",
        "-a",
        "-o",
        "-r",
        "-in",
        "-t",
        "--case",
        "--admin",
        "--owner",
        "--regex",
        "--contains",
        "--template",
    }

    for part in parts:
        if part in valid_flags:
            flags.append(part)
        else:
            key_parts.append(part)

    key_phrase = " ".join(key_parts)

    if not key_phrase:
        await message.answer(i18n.get("trigger-add-error"), parse_mode="HTML")
        return

    match_type = MatchType.EXACT
    is_case_sensitive = False
    access_level = AccessLevel.ALL
    is_template = False

    if "-c" in flags or "--case" in flags:
        is_case_sensitive = True

    if "-r" in flags or "--regex" in flags:
        match_type = MatchType.REGEXP
    elif "-in" in flags or "--contains" in flags:
        match_type = MatchType.CONTAINS

    if "-a" in flags or "--admin" in flags:
        access_level = AccessLevel.ADMINS
    elif "-o" in flags or "--owner" in flags:
        access_level = AccessLevel.OWNER

    if "-t" in flags or "--template" in flags:
        is_template = True

    user_member = await message.chat.get_member(message.from_user.id)
    is_admin = user_member.status in ("administrator", "creator")

    if db_chat.admins_only_add and not is_admin:
        await message.answer(i18n.get("error-no-rights"), parse_mode="HTML")
        return

    content = json.loads(message.reply_to_message.model_dump_json(exclude_unset=True, exclude_defaults=True))

    if is_template:
        template_text = content.get("text") or content.get("caption")
        if template_text:
            try:
                validate_template(template_text)
            except ValueError as e:
                await message.answer(f"Ошибка валидации шаблона: {e!s}", parse_mode="HTML")
                return

    skip_moderation = False
    if db_chat.is_trusted:
        skip_moderation = True
    else:
        if user.is_trusted or user.is_bot_moderator or user.id in settings.BOT_ADMINS:
            skip_moderation = True

    try:
        await create_trigger(
            session=session,
            chat_id=message.chat.id,
            key_phrase=key_phrase,
            content=content,
            match_type=match_type,
            is_case_sensitive=is_case_sensitive,
            access_level=access_level,
            created_by=message.from_user.id,
            skip_moderation=skip_moderation,
            is_template=is_template,
        )
        await message.answer(
            i18n.get("trigger-added", trigger_key=html.escape(key_phrase)),
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Error adding trigger")
        await message.answer(i18n.get("trigger-add-error"), parse_mode="HTML")
