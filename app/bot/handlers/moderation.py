import html
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.instance import bot
from app.core.broker import broker
from app.core.config import settings
from app.core.database import engine
from app.core.i18n import translator_hub
from app.db.models.chat import BannedChat, Chat
from app.db.models.trigger import ModerationStatus, Trigger
from app.schemas.moderation import ModerationAlert

logger = logging.getLogger(__name__)
router = Router()

# We need a session maker here because the subscriber runs in background
async_session = async_sessionmaker(engine, expire_on_commit=False)


def get_content_info(trigger: Trigger) -> tuple[str, str]:
    """Получить информацию о содержимом триггера."""
    content_data = trigger.content
    content_type = "Текст"
    content_text = content_data.get("text") or content_data.get("caption") or ""

    if content_data.get("photo"):
        content_type = "Фото"
    elif content_data.get("video"):
        content_type = "Видео"
    elif content_data.get("sticker"):
        content_type = "Стикер"
    elif content_data.get("document"):
        content_type = "Документ"
    elif content_data.get("animation"):
        content_type = "GIF"
    elif content_data.get("voice"):
        content_type = "Голосовое"
    elif content_data.get("audio"):
        content_type = "Аудио"

    return content_type, content_text


async def update_moderation_message(message: Message, text_append: str) -> None:
    """Обновить сообщение модерации (текст или подпись)."""
    try:
        # html_text returns the text or caption with HTML formatting
        new_text = f"{message.html_text}\n\n{text_append}"
        if message.caption:
            await message.edit_caption(caption=new_text, parse_mode="HTML")
        else:
            await message.edit_text(text=new_text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to update moderation message: {e}")


@broker.subscriber("q.moderation.alerts")
async def handle_moderation_alert(alert: ModerationAlert) -> None:
    logger.info(f"Received alert for trigger {alert.trigger_id}")

    # Fetch trigger details to show in message
    async with async_session() as session:
        trigger = await session.get(Trigger, alert.trigger_id)
        if not trigger:
            return

        # Get translator
        i18n = translator_hub.get_translator_by_locale("ru")

        # Extract content info
        content_type, content_text = get_content_info(trigger)

        # Prepare message
        text = i18n.get(
            "moderation-alert",
            category=alert.category,
            confidence=alert.confidence or "N/A",
            chat_id=alert.chat_id,
            trigger_id=alert.trigger_id,
            trigger_key=html.escape(trigger.key_phrase),
            content_type=content_type,
            content_text=html.escape(content_text),
            reasoning=alert.reasoning or "N/A",
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

        # Determine media type and file_id
        media_type = None
        file_id = None
        content_data = trigger.content

        if content_data.get("photo"):
            media_type = "photo"
            file_id = content_data["photo"][-1]["file_id"]
        elif content_data.get("video"):
            media_type = "video"
            file_id = content_data["video"]["file_id"]
        elif content_data.get("sticker"):
            media_type = "sticker"
            file_id = content_data["sticker"]["file_id"]
        elif content_data.get("document"):
            media_type = "document"
            file_id = content_data["document"]["file_id"]
        elif content_data.get("animation"):
            media_type = "animation"
            file_id = content_data["animation"]["file_id"]
        elif content_data.get("voice"):
            media_type = "voice"
            file_id = content_data["voice"]["file_id"]
        elif content_data.get("audio"):
            media_type = "audio"
            file_id = content_data["audio"]["file_id"]

        try:
            chat_id = settings.MODERATION_CHANNEL_ID

            if media_type == "sticker":
                await bot.send_sticker(chat_id=chat_id, sticker=file_id)
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            elif media_type == "photo":
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=file_id,
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            elif media_type == "video":
                await bot.send_video(
                    chat_id=chat_id,
                    video=file_id,
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            elif media_type == "animation":
                await bot.send_animation(
                    chat_id=chat_id,
                    animation=file_id,
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            elif media_type == "document":
                await bot.send_document(
                    chat_id=chat_id,
                    document=file_id,
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            elif media_type == "voice":
                await bot.send_voice(
                    chat_id=chat_id,
                    voice=file_id,
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            elif media_type == "audio":
                await bot.send_audio(
                    chat_id=chat_id,
                    audio=file_id,
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            else:
                # Text or unknown
                await bot.send_message(
                    chat_id=chat_id,
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

        await update_moderation_message(callback.message, f"✅ <b>Marked SAFE by {callback.from_user.username}</b>")

    else:
        await callback.answer("Trigger not found")


@router.callback_query(F.data.startswith("mod_del:"))
async def delete_trigger(callback: CallbackQuery, session: AsyncSession) -> None:
    trigger_id = int(callback.data.split(":")[1])

    trigger = await session.get(Trigger, trigger_id)
    if trigger:
        # Get info before deletion
        chat_id = trigger.chat_id
        key_phrase = trigger.key_phrase
        content_type, content_text = get_content_info(trigger)

        await session.delete(trigger)
        await session.commit()

        await update_moderation_message(callback.message, f"💀 <b>Deleted by {callback.from_user.username}</b>")

        # Notify user
        chat = await session.get(Chat, chat_id)
        lang = chat.language_code if chat else "ru"
        i18n = translator_hub.get_translator_by_locale(lang)

        text = i18n.get(
            "moderation-declined",
            trigger_key=html.escape(key_phrase),
            content_type=content_type,
            content_text=html.escape(content_text),
            reason="Moderation",
        )

        try:
            await bot.send_message(chat_id, text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to notify chat {chat_id}: {e}")

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

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        logger.info(f"Chat {chat_id} is already banned. Proceeding to delete trigger.")

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

    await update_moderation_message(callback.message, f"☢️ <b>Chat BANNED by {callback.from_user.username}</b>")
