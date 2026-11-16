import html
import json
import logging

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from fluentogram import TranslatorRunner
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.member_status import is_chat_admin
from app.core.config import settings
from app.db.models.chat import Chat
from app.db.models.trigger import AccessLevel, MatchType
from app.db.models.user import User
from app.services.rich_html import RichHtmlError, validate_rich_html
from app.services.template_service import validate_template
from app.services.trigger_service import DuplicateTriggerError, create_trigger, validate_regex

logger = logging.getLogger(__name__)
router = Router()

# Что бот умеет отправить повторно (Message.send_copy + send_dice). Всё остальное --
# служебные сообщения (вход/выход, закреп, темы, видеочаты), платные медиа, розыгрыши --
# Telegram копировать не даёт, и такой триггер никогда бы не ответил.
COPYABLE_CONTENT_KEYS = (
    "text",
    "audio",
    "animation",
    "document",
    "live_photo",
    "photo",
    "sticker",
    "video",
    "video_note",
    "voice",
    "contact",
    "venue",
    "location",
    "poll",
    "dice",
)


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
        await message.answer(i18n.trigger.add.error(), parse_mode="HTML")
        return

    args = command.args
    if not args:
        await message.answer(i18n.add.usage(), parse_mode="HTML")
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
        "-rh",
        "--case",
        "--admin",
        "--owner",
        "--regex",
        "--contains",
        "--template",
        "--rich",
    }

    for part in parts:
        if part in valid_flags:
            flags.append(part)
        else:
            key_parts.append(part)

    key_phrase = " ".join(key_parts)

    if not key_phrase:
        await message.answer(i18n.trigger.add.error(), parse_mode="HTML")
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

    rich = "-rh" in flags or "--rich" in flags
    if rich:
        is_template = True

    if db_chat.admins_only_add and not await is_chat_admin(message):
        await message.answer(i18n.error.no.rights(), parse_mode="HTML")
        return

    content = json.loads(message.reply_to_message.model_dump_json(exclude_unset=True))

    if not any(content.get(key) for key in COPYABLE_CONTENT_KEYS):
        await message.answer(i18n.trigger.add.unsupported(), parse_mode="HTML")
        return

    if match_type == MatchType.REGEXP:
        regex_error = await validate_regex(key_phrase)
        if regex_error:
            await message.answer(i18n.trigger.validation.error(error=regex_error), parse_mode="HTML")
            return

    if is_template:
        template_text = content.get("text") or content.get("caption")
        if template_text:
            try:
                validate_template(template_text)
            except ValueError as e:
                await message.answer(i18n.trigger.validation.error(error=str(e)), parse_mode="HTML")
                return

            if rich:
                try:
                    validate_rich_html(template_text)
                except RichHtmlError as e:
                    await message.answer(i18n.trigger.validation.error(error=str(e)), parse_mode="HTML")
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
            rich=rich,
        )
        await message.answer(
            i18n.trigger.added(trigger_key=html.escape(key_phrase)),
            parse_mode="HTML",
        )
    except DuplicateTriggerError as e:
        await message.answer(
            i18n.trigger.duplicate(trigger_key=html.escape(key_phrase), trigger_id=e.existing_id),
            parse_mode="HTML",
        )
    except Exception:
        logger.exception("Error adding trigger")
        await message.answer(i18n.trigger.add.error(), parse_mode="HTML")
