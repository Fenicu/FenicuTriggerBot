import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.instance import bot
from app.core.broker import broker
from app.core.config import settings
from app.core.database import engine
from app.db.models.chat import BannedChat
from app.db.models.trigger import ModerationStatus, Trigger
from app.schemas.moderation import ModerationAlert

logger = logging.getLogger(__name__)
router = Router()

# We need a session maker here because the subscriber runs in background
async_session = async_sessionmaker(engine, expire_on_commit=False)


@broker.subscriber("q.moderation.alerts")
async def handle_moderation_alert(alert: ModerationAlert) -> None:
    logger.info(f"Received alert for trigger {alert.trigger_id}")

    # Fetch trigger details to show in message
    async with async_session() as session:
        trigger = await session.get(Trigger, alert.trigger_id)
        if not trigger:
            return

        # Prepare message
        text = (
            f"🚨 <b>Подозрительный триггер</b>\n\n"
            f"Категория: {alert.category} (conf: {alert.confidence or 'N/A'})\n"
            f"Чат: {alert.chat_id}\n"
            f"ID: {alert.trigger_id}\n\n"
            f"Ключ: {trigger.key_phrase}\n"
            f"Причина: {alert.reasoning or 'N/A'}"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Ложная тревога", callback_data=f"mod_safe:{alert.trigger_id}")],
                [InlineKeyboardButton(text="💀 Удалить триггер", callback_data=f"mod_del:{alert.trigger_id}")],
                [
                    InlineKeyboardButton(
                        text="☢️ Забанить чат",
                        callback_data=f"mod_ban:{alert.chat_id}:{alert.trigger_id}",
                    )
                ],
            ]
        )

        try:
            await bot.send_message(
                chat_id=settings.MODERATION_CHANNEL_ID,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error(f"Failed to send alert to moderation channel: {e}")


# Callback handlers
@router.callback_query(F.data.startswith("mod_safe:"))
async def mark_safe(callback: CallbackQuery, session: AsyncSession) -> None:
    trigger_id = int(callback.data.split(":")[1])

    trigger = await session.get(Trigger, trigger_id)
    if trigger:
        trigger.moderation_status = ModerationStatus.SAFE
        trigger.moderation_reason = f"False positive (marked by {callback.from_user.username})"
        await session.commit()

        await callback.message.edit_text(
            f"{callback.message.html_text}\n\n✅ <b>Marked SAFE by {callback.from_user.username}</b>",
            parse_mode="HTML",
        )
    else:
        await callback.answer("Trigger not found")


@router.callback_query(F.data.startswith("mod_del:"))
async def delete_trigger(callback: CallbackQuery, session: AsyncSession) -> None:
    trigger_id = int(callback.data.split(":")[1])

    trigger = await session.get(Trigger, trigger_id)
    if trigger:
        await session.delete(trigger)
        await session.commit()

        await callback.message.edit_text(
            f"{callback.message.html_text}\n\n💀 <b>Deleted by {callback.from_user.username}</b>",
            parse_mode="HTML",
        )
    else:
        await callback.answer("Trigger already deleted")


@router.callback_query(F.data.startswith("mod_ban:"))
async def ban_chat(callback: CallbackQuery, session: AsyncSession) -> None:
    _, chat_id, trigger_id = callback.data.split(":")
    chat_id = int(chat_id)
    trigger_id = int(trigger_id)

    # Ban chat
    banned = BannedChat(
        chat_id=chat_id,
        reason=f"Banned via moderation trigger {trigger_id} by {callback.from_user.username}",
    )
    session.add(banned)

    # Delete trigger
    trigger = await session.get(Trigger, trigger_id)
    if trigger:
        await session.delete(trigger)

    await session.commit()

    # Leave chat
    try:
        await bot.leave_chat(chat_id)
    except Exception as e:
        logger.error(f"Failed to leave chat {chat_id}: {e}")

    await callback.message.edit_text(
        f"{callback.message.html_text}\n\n☢️ <b>Chat BANNED by {callback.from_user.username}</b>",
        parse_mode="HTML",
    )
