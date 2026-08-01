import html
import logging
from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaAnimation,
    InputMediaAudio,
    InputMediaPhoto,
    InputMediaVideo,
    InputMediaVoiceNote,
    InputRichMessage,
    InputRichMessageMedia,
    Message,
)
from faststream.rabbit import RabbitQueue
from fluentogram import TranslatorRunner
from sqlalchemy import update
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
from app.services.chat_trust_service import register_false_positive
from app.services.deeplink_service import build_chat_deeplink
from app.services.moderation_history_service import add_history_step
from app.services.preview_service import generate_preview_url
from app.services.rich_html import _VOID_TAGS, rich_message_to_html
from app.services.trigger_service import delete_trigger_by_id, get_file_info_from_content

logger = logging.getLogger(__name__)
router = Router()

async_session = async_sessionmaker(engine, expire_on_commit=False)

_ALERT_FIELD_LIMIT = 3000

# Типы медиа, эмбеддируемые прямо в rich-карточку (Bot API 10.2): file_type ->
# (InputMedia*-класс, HTML-тег, tg://-схема для src). Остальные типы (document,
# sticker, video_note) идут legacy-путём — отдельным сообщением рядом с алертом.
_EMBEDDABLE: dict[str, tuple[type, str, str]] = {
    "photo": (InputMediaPhoto, "img", "tg://photo?id="),
    "video": (InputMediaVideo, "video", "tg://video?id="),
    "animation": (InputMediaAnimation, "video", "tg://video?id="),
    "audio": (InputMediaAudio, "audio", "tg://audio?id="),
    "voice": (InputMediaVoiceNote, "audio", "tg://audio?id="),
}

_LEGACY_MEDIA_TYPES = frozenset({"document", "sticker", "video_note"})


def _clip(value: str) -> str:
    """Обрезать поле до лимита alert'а, добавив многоточие при превышении."""
    if not value:
        return "—"
    if len(value) > _ALERT_FIELD_LIMIT:
        return value[:_ALERT_FIELD_LIMIT] + "…"
    return value


def sanitize_redirect_chain(chain: list[str]) -> list[str]:
    """Урезать каждый URL цепочки до scheme+host+path, без query/fragment.

    В query нередко лежат трекинг-токены (affiliate id и т.п.) — карточка алерта их
    не показывает. В LLM-контекст (build_link_context) уходит полный URL, как раньше;
    эта функция применяется только здесь, при рендере карточки.
    """
    sanitized = []
    for url in chain:
        parsed = urlparse(url)
        # hostname (не netloc) -- netloc сохраняет user:password@, credentials в карточке лишние
        host_port = parsed.hostname or ""
        if parsed.port:
            host_port += f":{parsed.port}"
        sanitized.append(f"{parsed.scheme}://{host_port}{parsed.path}")
    return sanitized


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
    transcript: str | None = None,
    redirect_chain: list[str] | None = None,
) -> str:
    """Собрать rich-HTML (Bot API 10.1) сообщение модерации."""
    category = html.escape(str(category), quote=False)
    confidence = html.escape(str(confidence), quote=False)
    content_type = html.escape(str(content_type), quote=False)
    trigger_key = html.escape(str(trigger_key), quote=False)
    content_text = _clip(html.escape(str(content_text), quote=False) if content_text else "")
    reasoning = _clip(html.escape(str(reasoning), quote=False) if reasoning else "")
    transcript_block = ""
    if transcript:
        transcript = _clip(html.escape(str(transcript), quote=False))
        transcript_block = f"<details><summary>🎤 Распознанная речь</summary><p>{transcript}</p></details>"

    redirect_block = ""
    if redirect_chain:
        chain_html = " -> ".join(html.escape(u, quote=False) for u in sanitize_redirect_chain(redirect_chain))
        redirect_block = f"<details><summary>🔗 Цепочка редиректов</summary><p>{chain_html}</p></details>"

    return (
        "<h3>🚨 Подозрительный триггер</h3>"
        f"<blockquote><p><b>Категория:</b> {category} · <b>уверенность:</b> {confidence}</p></blockquote>"
        f"<p><b>Чат:</b> <code>{chat_id}</code> · <b>ID:</b> <code>{trigger_id}</code></p>"
        f"<p><b>Ключ:</b> {trigger_key}<br><b>Тип:</b> {content_type}</p>"
        f"<details><summary>📄 Содержание</summary><p>{content_text}</p></details>"
        f"{transcript_block}"
        f"{redirect_block}"
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


# Синтетический id медиа-элемента в InputRichMessageMedia/tg://-src. Карточка модерации
# всегда несёт максимум одно эмбеддируемое медиа, поэтому id может быть константой — реальный
# Telegram file_id часто длиннее 64 символов и вне алфавита [A-Za-z0-9_-] (см. _TG_SRC_RE),
# так что использовать его напрямую как id/src нельзя.
_MEDIA_ID = "m0"


def build_alert_media(file_id: str | None, media_type: str | None) -> tuple[list[InputRichMessageMedia], str]:
    """Собрать rich-медиа и tg://-HTML-фрагмент для эмбеддируемого медиа триггера.

    Принимает уже вычисленные (file_id, media_type) — вызывающий код (handle_moderation_alert /
    update_moderation_message) считает их через get_file_info_from_content один раз.
    Для legacy-типов (document/sticker/video_note) и триггеров без медиа возвращает
    пустой список и пустую строку — такое медиа отправляется отдельным сообщением
    (см. handle_moderation_alert), в rich-карточку не встраивается.
    """
    if not file_id or media_type not in _EMBEDDABLE:
        return [], ""

    media_cls, tag, scheme = _EMBEDDABLE[media_type]
    media = [InputRichMessageMedia(id=_MEDIA_ID, media=media_cls(media=file_id))]
    src = f"{scheme}{_MEDIA_ID}"
    media_html = f'<{tag} src="{src}">' if tag in _VOID_TAGS else f'<{tag} src="{src}"></{tag}>'
    return media, media_html


async def _send_media_message(chat_id: int, media_type: str, file_id: str) -> None:
    """Отправить медиа отдельным сообщением (legacy-путь для document/sticker/video_note,
    либо fallback-путь для эмбеддируемых типов при сбое rich-отправки)."""
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
        elif media_type == "video_note":
            await bot.send_video_note(chat_id=chat_id, video_note=file_id)
    except Exception as e:
        logger.error("Failed to send media to moderation channel: %s", e)


async def update_moderation_message(message: Message, status_html: str, trigger_content: dict | None = None) -> None:
    """Append a moderation status line to the alert message (rich or legacy), preserving media.

    rich_message_to_html выбрасывает медиа-блоки при сериализации существующего сообщения —
    build_alert_media восстанавливает и сам tg://-фрагмент, и объект media для edit_text.
    Сбой rich-редактирования с media -> fallback: тот же edit ещё раз, но без media_html-
    фрагмента и без media (только если и он упадёт — логируем и сдаёмся).
    """
    try:
        if message.rich_message is not None:
            file_id, media_type = get_file_info_from_content(trigger_content) if trigger_content else (None, None)
            media, media_html = build_alert_media(file_id, media_type)
            base = rich_message_to_html(message.rich_message)
            new_html = f"{media_html}{base}<hr><p>{status_html}</p>"
            try:
                await message.edit_text(rich_message=InputRichMessage(html=new_html, media=media or None))
            except Exception as e:
                logger.error("Failed to update moderation message with media, retrying without media: %s", e)
                fallback_html = f"{base}<hr><p>{status_html}</p>"
                try:
                    await message.edit_text(rich_message=InputRichMessage(html=fallback_html))
                except Exception as e2:
                    logger.error("Failed to update moderation message (fallback without media): %s", e2)
        else:
            new_text = f"{message.html_text}\n\n{status_html}"
            await message.edit_text(text=new_text, parse_mode="HTML")
    except Exception as e:
        logger.error("Failed to update moderation message: %s", e)


@broker.subscriber(RabbitQueue("q.moderation.alerts", durable=False))
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
            transcript=alert.transcript,
            redirect_chain=alert.redirect_chain,
        )

        chat_deeplink = await build_chat_deeplink(alert.chat_id)

        inline_keyboard: list[list[InlineKeyboardButton]] = []
        if chat_deeplink is not None:
            inline_keyboard.append([InlineKeyboardButton(text="💬 Карточка чата", url=chat_deeplink)])
        inline_keyboard.extend(
            [
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
        keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

        chat_id = settings.MODERATION_CHANNEL_ID
        content_data = trigger.content
        file_id, media_type = get_file_info_from_content(content_data)
        media, media_html = build_alert_media(file_id, media_type)

        # Legacy media (document/sticker/video_note) is not embeddable — sent separately,
        # right away, regardless of how the rich-send below goes.
        if file_id and media_type in _LEGACY_MEDIA_TYPES:
            await _send_media_message(chat_id, media_type, file_id)

        # Send rich alert with buttons; embeddable media (photo/video/animation/audio/voice)
        # rides inside the same message via InputRichMessage.media + tg://-src in the html.
        try:
            await bot.send_rich_message(
                chat_id=chat_id,
                rich_message=InputRichMessage(html=f"{media_html}{rich_html}", media=media or None),
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error("Failed to send rich alert to moderation channel: %s", e)
            # Fallback: legacy two-step path — media (if not already sent above) as a
            # separate message, then the rich alert again WITHOUT media/tg://-fragment.
            if file_id and media_type and media_type not in _LEGACY_MEDIA_TYPES:
                await _send_media_message(chat_id, media_type, file_id)
            try:
                await bot.send_rich_message(
                    chat_id=chat_id,
                    rich_message=InputRichMessage(html=rich_html),
                    reply_markup=keyboard,
                )
            except Exception as e2:
                logger.error("Failed to send fallback rich alert to moderation channel: %s", e2)


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
    previous_status = trigger.moderation_status
    if previous_status not in (ModerationStatus.FLAGGED, ModerationStatus.ERROR):
        await callback.answer("Already handled by another moderator", show_alert=True)
        return

    was_flagged = previous_status == ModerationStatus.FLAGGED
    reason = f"False positive (marked by {user_name})"

    # Условный UPDATE вместо read-then-write: если несколько модераторов одновременно жмут
    # «ложная тревога» на одном триггере, только первый найдёт статус нетронутым и пройдёт
    # (см. defect #2 ревью) -- остальные получат rowcount=0 и не задвоят счётчик.
    stmt = (
        update(Trigger)
        .where(Trigger.id == trigger_id, Trigger.moderation_status == previous_status)
        .values(moderation_status=ModerationStatus.SAFE, moderation_reason=reason)
    )
    result = await session.execute(stmt)
    if result.rowcount != 1:
        await callback.answer("Already handled by another moderator", show_alert=True)
        return

    trigger.moderation_status = ModerationStatus.SAFE
    trigger.moderation_reason = reason
    await add_history_step(
        session,
        trigger_id,
        ModerationStep.MANUAL_APPROVED,
        details={"marked_by": user_name, "was_false_positive": True},
        actor_id=callback.from_user.id,
    )

    if was_flagged:
        # register_false_positive коммитит сессию сам -- статус триггера и учёт репутации
        # уходят одной транзакцией (см. defect #4 ревью).
        try:
            await register_false_positive(session, trigger.chat_id)
        except Exception as e:
            logger.warning("Failed to register false positive for chat %s: %s", trigger.chat_id, e)
    else:
        await session.commit()

    await callback.answer("Marked as safe")
    await update_moderation_message(
        callback.message, f"✅ Marked SAFE by <b>{html.escape(user_name)}</b>", trigger.content
    )


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
    await update_moderation_message(callback.message, f"💀 Deleted by <b>{html.escape(user_name)}</b>", trigger.content)

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
    await update_moderation_message(
        callback.message,
        f"☢️ Chat BANNED by <b>{html.escape(user_name)}</b>",
        trigger.content if trigger else None,
    )
