import logging
import re
from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from fluentogram import TranslatorRunner
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.instance import bot
from app.db.models.chat import Chat
from app.db.models.user_chat import UserChat
from app.services.reputation_service import (
    get_active_users_count,
    get_level_name,
    get_thresholds,
    get_user_rank,
)
from app.services.tag_service import clear_manual_tag, set_manual_tag

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("status"))
async def status_command(
    message: Message,
    session: AsyncSession,
    i18n: TranslatorRunner,
    db_chat: Chat,
) -> None:
    """Показать репутационный статус пользователя."""
    if message.chat.type not in ("group", "supergroup"):
        await message.answer(i18n.reputation.group.only(), parse_mode="HTML")
        return

    if not db_chat.tags_enabled:
        await message.answer(i18n.reputation.disabled(), parse_mode="HTML")
        return

    user_id = message.from_user.id
    user_chat = await session.get(UserChat, (user_id, db_chat.id))

    if not user_chat:
        await message.answer(i18n.reputation.no.data(), parse_mode="HTML")
        return

    thresholds = get_thresholds(db_chat)
    level = user_chat.reputation_level
    level_name = get_level_name(level, db_chat)
    score = user_chat.reputation_score

    # Прогресс до следующего уровня
    if level < len(thresholds):
        next_threshold = thresholds[level]
        prev_threshold = thresholds[level - 1] if level > 0 else 0
        progress_current = score - prev_threshold
        progress_total = next_threshold - prev_threshold
        progress_pct = min(int(progress_current / progress_total * 100), 99) if progress_total > 0 else 0
        remaining = next_threshold - score
        progress_bar = _make_progress_bar(progress_pct)
        next_info = i18n.reputation.next.level(remaining=remaining)
    else:
        progress_pct = 100
        progress_bar = _make_progress_bar(100)
        next_info = i18n.reputation.max.level()

    rank = await get_user_rank(session, db_chat.id, user_id)
    total_users = await get_active_users_count(session, db_chat.id)

    text = i18n.reputation.status(
        level_name=level_name or "—",
        level=level,
        score=score,
        progress_bar=progress_bar,
        progress_pct=progress_pct,
        next_info=next_info,
        rank=rank or 0,
        total=total_users,
    )

    await message.answer(text, parse_mode="HTML")


@router.message(Command("tag"))
async def tag_command(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    i18n: TranslatorRunner,
    db_chat: Chat,
) -> None:
    """Установить ручной тег пользователю (только для админов)."""
    if message.chat.type not in ("group", "supergroup"):
        return

    user_member = await message.chat.get_member(message.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await message.answer(i18n.error.no.rights(), parse_mode="HTML")
        return

    if not command.args:
        await message.answer(i18n.tag.usage(), parse_mode="HTML")
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer(i18n.tag.reply.required(), parse_mode="HTML")
        return

    target_user = message.reply_to_message.from_user
    tag_text = command.args.strip()[:16]

    if not re.match(r'^[\w\s\-]+$', tag_text, re.UNICODE):
        await message.answer(i18n.tag.invalid(), parse_mode="HTML")
        return

    user_chat = await session.get(UserChat, (target_user.id, db_chat.id))
    if not user_chat:
        await message.answer(i18n.user.missing(), parse_mode="HTML")
        return

    success = await set_manual_tag(bot, session, user_chat, db_chat.id, tag_text)
    if not success:
        await message.answer(i18n.error.unknown(), parse_mode="HTML")
        return

    await message.answer(
        i18n.tag.set(user=target_user.mention_html(), tag=escape(tag_text)),
        parse_mode="HTML",
    )


@router.message(Command("deltag"))
async def deltag_command(
    message: Message,
    session: AsyncSession,
    i18n: TranslatorRunner,
    db_chat: Chat,
) -> None:
    """Удалить ручной тег пользователя (только для админов)."""
    if message.chat.type not in ("group", "supergroup"):
        return

    user_member = await message.chat.get_member(message.from_user.id)
    if user_member.status not in ("administrator", "creator"):
        await message.answer(i18n.error.no.rights(), parse_mode="HTML")
        return

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer(i18n.tag.reply.required(), parse_mode="HTML")
        return

    target_user = message.reply_to_message.from_user
    user_chat = await session.get(UserChat, (target_user.id, db_chat.id))
    if not user_chat:
        await message.answer(i18n.user.missing(), parse_mode="HTML")
        return

    success = await clear_manual_tag(bot, session, user_chat, db_chat)
    if not success:
        await message.answer(i18n.error.unknown(), parse_mode="HTML")
        return

    await message.answer(
        i18n.tag.cleared(user=target_user.mention_html()),
        parse_mode="HTML",
    )


def _make_progress_bar(pct: int, length: int = 12) -> str:
    """Создать текстовый прогресс-бар."""
    filled = int(length * pct / 100)
    empty = length - filled
    return "█" * filled + "░" * empty
