import html
import logging

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
    Message,
)
from fluentogram import TranslatorRunner
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.instance import bot
from app.core.broker import broker
from app.core.config import settings
from app.core.database import engine
from app.core.i18n import ROOT_LOCALE, translator_hub
from app.db.models.chat import BannedChat, Chat
from app.db.models.moderation_history import ModerationStep
from app.db.models.trigger import ModerationStatus, Trigger
from app.schemas.moderation import ModerationAlert
from app.services.moderation_history_service import add_history_step
from app.services.preview_service import generate_preview_url
from app.services.rich_html import rich_message_to_html
from app.services.trigger_service import delete_trigger_by_id, get_file_info_from_content

logger = logging.getLogger(__name__)
router = Router()

async_session = async_sessionmaker(engine, expire_on_commit=False)

_ALERT_FIELD_LIMIT = 3000


def _clip(value: str) -> str:
    """Обрезать поле до лимита alert'а, добавив многоточие при превышении."""
    if not value:
        return "—"
    if len(value) > _ALERT_FIELD_LIMIT:
        return value[:_ALERT_FIELD_LIMIT] + "…"
    return value


def build_alert_rich_html(
    *,
    category: str,
    confidence: object,
    chat_id: int,
    trigger_id: int,
    trigger_key: str,
    content_type: str,
    content_text: str | None,
    reasoning: str | None,
) -> str:
    """Собрать rich-HTML (Bot API 10.1) сообщение модерации."""
    category = html.escape(str(category), quote=False)
    confidence = html.escape(str(confidence), quote=False)
    content_type = html.escape(str(content_type), quote=False)
    trigger_key = html.escape(str(trigger_key), quote=False)
    content_text = _clip(html.escape(str(content_text), quote=False) if content_text else "")
    reasoning = _clip(html.escape(str(reasoning), quote=False) if reasoning else "")

    return (
        "<h3>🚨 Подозрительный триггер</h3>"
        f"<blockquote><p><b>Категория:</b> {category} · <b>уверенность:</b> {confidence}</p></blockquote>"
        f"<p><b>Чат:</b> <code>{chat_id}</code> · <b>ID:</b> <code>{trigger_id}</code></p>"
        f"<p><b>Ключ:</b> {trigger_key}<br><b>Тип:</b> {content_type}</p>"
        f"<details><summary>📄 Содержание</summary><p>{content_text}</p></details>"
        f"<details><summary>🧠 Заключение модели</summary><p>{reasoning}</p></details>"
    )


def get_content_info(trigger: Trigger, i18n: TranslatorRunner) -> tuple[str, str]:
    """Получить информацию о содержимом триггера."""
    content_data = trigger.content
    content_type = i18n.content.type.text()
    content_text = content_data.get("text") or content_data.get("caption") or ""

    if content_data.get("photo"):
        content_type = i18n.content.type.photo()
    elif content_data.get("video"):
        content_type = i18n.content.type.video()
    elif content_data.get("sticker"):
        content_type = i18n.content.type.sticker()
    elif content_data.get("document"):
        content_type = i18n.content.type.document()
    elif content_data.get("animation"):
        content_type = i18n.content.type.gif()
    elif content_data.get("voice"):
        content_type = i18n.content.type.voice()
    elif content_data.get("audio"):
        content_type = i18n.content.type.audio()

    return content_type, content_text


async def update_moderation_message(message: Message, status_html: str) -> None:
    """Append a moderation status line to the alert message (rich or legacy)."""
    try:
        if message.rich_message is not None:
            base = rich_message_to_html(message.rich_message)
            new_html = f"{base}<hr><p>{status_html}</p>"
            await message.edit_text(rich_message=InputRichMessage(html=new_html))
        else:
            new_text = f"{message.html_text}\n\n{status_html}"
            await message.edit_text(text=new_text, parse_mode="HTML")
    except Exception as e:
        logger.error("Failed to update moderation message: %s", e)


@broker.subscriber("q.moderation.alerts")
async def handle_moderation_alert(alert: ModerationAlert) -> None:
    logger.info("Received alert for trigger %d", alert.trigger_id)

    async with async_session() as session:
        trigger = await session.get(Trigger, alert.trigger_id)
        if not trigger:
            return

        i18n = translator_hub.get_translator_by_locale(ROOT_LOCALE)

        content_type, content_text = get_content_info(trigger, i18n)

        preview_url = generate_preview_url(alert.trigger_id)

        rich_html = build_alert_rich_html(
            category=alert.category,
            confidence=alert.confidence if alert.confidence is not None else "N/A",
            chat_id=alert.chat_id,
            trigger_id=alert.trigger_id,
            trigger_key=trigger.key_phrase,
            content_type=content_type,
            content_text=content_text,
            reasoning=alert.reasoning,
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔍 Полный предпросмотр", url=preview_url)],
                [InlineKeyboardButton(text=i18n.btn.false.alarm(), callback_data=f"mod_safe:{alert.trigger_id}")],
                [InlineKeyboardButton(text=i18n.btn.delete.trigger(), callback_data=f"mod_del:{alert.trigger_id}")],
                [
                    InlineKeyboardButton(
                        text=i18n.btn.ban.chat(),
                        callback_data=f"mod_ban:{alert.chat_id}:{alert.trigger_id}",
                    )
                ],
            ]
        )

        chat_id = settings.MODERATION_CHANNEL_ID
        content_data = trigger.content
        file_id, media_type = get_file_info_from_content(content_data)

        # Step 1: Send media separately (if any)
        if file_id and media_type:
            try:
                if media_type == "sticker":
                    await bot.send_sticker(chat_id=chat_id, sticker=file_id)
                elif media_type == "photo":
                    await bot.send_photo(chat_id=chat_id, photo=file_id)
                elif media_type == "video":
                    await bot.send_video(chat_id=chat_id, video=file_id)
                elif media_type == "animation":
                    await bot.send_animation(chat_id=chat_id, animation=file_id)
                elif media_type == "document":
                    await bot.send_document(chat_id=chat_id, document=file_id)
                elif media_type == "voice":
                    await bot.send_voice(chat_id=chat_id, voice=file_id)
                elif media_type == "audio":
                    await bot.send_audio(chat_id=chat_id, audio=file_id)
            except Exception as e:
                logger.error("Failed to send media to moderation channel: %s", e)

        # Step 2: Send rich alert with buttons
        try:
            await bot.send_rich_message(
                chat_id=chat_id,
                rich_message=InputRichMessage(html=rich_html),
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error("Failed to send rich alert to moderation channel: %s", e)


@router.callback_query(F.data.startswith("mod_safe:"))
async def mark_safe(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        trigger_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Invalid data")
        return
    user_name = callback.from_user.username or callback.from_user.full_name

    trigger = await session.get(Trigger, trigger_id)
    if not trigger:
        await callback.answer("Trigger not found")
        return
    if trigger.moderation_status not in (ModerationStatus.FLAGGED, ModerationStatus.ERROR):
        await callback.answer("Already handled by another moderator", show_alert=True)
        return

    trigger.moderation_status = ModerationStatus.SAFE
    trigger.moderation_reason = f"False positive (marked by {user_name})"
    await add_history_step(
        session,
        trigger_id,
        ModerationStep.MANUAL_APPROVED,
        details={"marked_by": user_name, "was_false_positive": True},
        actor_id=callback.from_user.id,
    )
    await session.commit()

    await callback.answer("Marked as safe")
    await update_moderation_message(callback.message, f"✅ Marked SAFE by <b>{html.escape(user_name)}</b>")


@router.callback_query(F.data.startswith("mod_del:"))
async def delete_trigger(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        trigger_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Invalid data")
        return
    user_name = callback.from_user.username or callback.from_user.full_name

    trigger = await session.get(Trigger, trigger_id)
    if not trigger:
        await callback.answer("Trigger already deleted")
        return
    if trigger.moderation_status not in (ModerationStatus.FLAGGED, ModerationStatus.ERROR):
        await callback.answer("Already handled by another moderator", show_alert=True)
        return

    chat_id = trigger.chat_id
    key_phrase = trigger.key_phrase

    chat = await session.get(Chat, chat_id)
    lang = chat.language_code if chat else ROOT_LOCALE
    i18n = translator_hub.get_translator_by_locale(lang)

    content_type, content_text = get_content_info(trigger, i18n)

    await add_history_step(
        session,
        trigger_id,
        ModerationStep.MANUAL_DELETED,
        details={"deleted_by": user_name},
        actor_id=callback.from_user.id,
    )
    await delete_trigger_by_id(session, trigger.id)

    await callback.answer("Trigger deleted")
    await update_moderation_message(callback.message, f"💀 Deleted by <b>{html.escape(user_name)}</b>")

    text = i18n.moderation.declined(
        trigger_key=html.escape(key_phrase),
        content_type=content_type,
        content_text=html.escape(content_text),
        reason="Moderation",
    )

    try:
        await bot.send_message(chat_id, text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to notify chat {chat_id}: {e}")


@router.callback_query(F.data.startswith("mod_ban:"))
async def ban_chat(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        _, chat_id_str, trigger_id_str = callback.data.split(":")
        chat_id = int(chat_id_str)
        trigger_id = int(trigger_id_str)
    except (ValueError, IndexError):
        await callback.answer("Invalid data")
        return
    user_name = callback.from_user.username or callback.from_user.full_name

    trigger = await session.get(Trigger, trigger_id)
    if not trigger:
        await callback.answer("Trigger not found")
        return
    if trigger.moderation_status not in (ModerationStatus.FLAGGED, ModerationStatus.ERROR):
        await callback.answer("Already handled by another moderator", show_alert=True)
        return

    banned = BannedChat(
        chat_id=chat_id,
        reason=f"Banned via moderation trigger {trigger_id} by {user_name}",
    )
    session.add(banned)

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        logger.info(f"Chat {chat_id} is already banned. Proceeding to delete trigger.")

    # Re-fetch trigger after potential rollback and re-check status
    trigger = await session.get(Trigger, trigger_id)
    if trigger and trigger.moderation_status in (ModerationStatus.FLAGGED, ModerationStatus.ERROR):
        await add_history_step(
            session,
            trigger_id,
            ModerationStep.MANUAL_BANNED,
            details={"banned_by": user_name, "chat_id": chat_id},
            actor_id=callback.from_user.id,
        )
        await delete_trigger_by_id(session, trigger.id)

    await session.commit()

    try:
        await bot.leave_chat(chat_id)
    except Exception as e:
        logger.warning(f"Failed to leave chat {chat_id}: {e}")

    await callback.answer("Chat banned")
    await update_moderation_message(callback.message, f"☢️ Chat BANNED by <b>{html.escape(user_name)}</b>")
