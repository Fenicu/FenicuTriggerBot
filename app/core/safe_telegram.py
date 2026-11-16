"""
Обёртки над Telegram Bot API с проверкой кэша прав.

Перед вызовом проверяют, не закэшировано ли нужное право как отсутствующее.
При ошибке "not enough rights" — кэшируют и возвращают None/False.
Работают как внутри dispatcher, так и в workers.
"""

import logging
from contextlib import suppress

from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.types import ChatPermissions, EphemeralMessageParameters, Message, ReplyParameters

from app.core import permissions
from app.core.broker import broker, delayed_exchange, schedule_autodelete

logger = logging.getLogger(__name__)

# Подстроки TelegramBadRequest, привязанные к конкретному топику/треду —
# можно молча пропустить, в кэш писать не нужно (другие топики того же чата работают).
_TOPIC_BAD_REQUEST_SUBSTRINGS = (
    "TOPIC_CLOSED",
    "MESSAGE_THREAD_NOT_FOUND",
)

# Подстроки TelegramBadRequest, означающие глобальный запрет писать в чат —
# эквивалент отсутствия can_send_messages, нужно кэшировать.
_NO_WRITE_BAD_REQUEST_SUBSTRINGS = ("CHAT_WRITE_FORBIDDEN",)


def is_topic_error(exc: BaseException) -> bool:
    """True для TelegramBadRequest по закрытому/удалённому топику или треду.

    Эти ошибки безопасно глушить даже на верхнем уровне: они относятся к конкретному
    топику, остальные топики того же чата работают, кэшировать ничего не нужно.
    """
    if not isinstance(exc, TelegramBadRequest):
        return False
    msg = str(exc)
    return any(token in msg for token in _TOPIC_BAD_REQUEST_SUBSTRINGS)


def full_permissions() -> ChatPermissions:
    """Все 15 полей True -- документированный способ Telegram снять все индивидуальные
    ограничения и удалить юзера из списка исключений чата."""
    return ChatPermissions(
        can_send_messages=True,
        can_send_audios=True,
        can_send_documents=True,
        can_send_photos=True,
        can_send_videos=True,
        can_send_video_notes=True,
        can_send_voice_notes=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_edit_tag=True,
        can_change_info=True,
        can_invite_users=True,
        can_pin_messages=True,
        can_manage_topics=True,
    )


def full_restrictions() -> ChatPermissions:
    """Все 15 полей False -- полный мьют. Telegram не импортирует can_send_messages=False
    в остальные send_*, поэтому одного поля мало: юзер сможет слать медиа и стикеры."""
    return ChatPermissions(
        can_send_messages=False,
        can_send_audios=False,
        can_send_documents=False,
        can_send_photos=False,
        can_send_videos=False,
        can_send_video_notes=False,
        can_send_voice_notes=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
        can_edit_tag=False,
        can_change_info=False,
        can_invite_users=False,
        can_pin_messages=False,
        can_manage_topics=False,
    )


async def handle_send_error(exc: Exception, chat_id: int) -> bool:
    """Признать known-ошибку отправки и обновить кэш прав, если применимо.

    Returns:
        True — ошибка ожидаемая (флуд-контроль, закрытый топик, отсутствие прав
        на отправку), вызывающий должен молча скипнуть.
        False — ошибка неизвестная, вызывающий должен обработать её сам.
    """
    if isinstance(exc, TelegramRetryAfter):
        logger.info(
            "Rate limited on send in chat %d, retry_after=%ds; skipping",
            chat_id,
            exc.retry_after,
        )
        return True
    if isinstance(exc, TelegramBadRequest):
        msg = str(exc)
        if any(token in msg for token in _TOPIC_BAD_REQUEST_SUBSTRINGS):
            logger.debug("Skipping send in chat %d: %s", chat_id, exc)
            return True
        if any(token in msg for token in _NO_WRITE_BAD_REQUEST_SUBSTRINGS):
            await permissions.record_missing(chat_id, "can_send_messages")
            logger.debug("Cached missing can_send_messages in chat %d: %s", chat_id, exc)
            return True
        perm = permissions.parse_missing_permission(msg)
        if perm:
            await permissions.record_missing(chat_id, perm)
            logger.debug("Cached missing permission %s in chat %d", perm, chat_id)
            return True
    return False


async def safe_send_message(bot: Bot, chat_id: int, **kwargs) -> Message | None:
    """Отправить сообщение. Возвращает Message или None если нет прав."""
    if await permissions.is_missing(chat_id, "can_send_messages"):
        return None
    try:
        return await bot.send_message(chat_id, **kwargs)
    except TelegramBadRequest as e:
        perm = permissions.parse_missing_permission(str(e))
        if perm:
            await permissions.record_missing(chat_id, perm)
            return None
        raise


async def ephemeral_answer(
    bot: Bot,
    message: Message,
    text: str,
    *,
    sensitive: bool = False,
    fallback_notice: str | None = None,
    autodelete: tuple[dict | None, str] | None = None,
    **kwargs,
) -> Message | None:
    """Персональный ответ на команду: эфемерно в группе, обычно в ЛС.

    В группе отправка требует бот-админа и получателя-участника чата (Bot API 10.2),
    поэтому при `(TelegramBadRequest, TelegramForbiddenError)` есть fallback:
    `sensitive=True` — сначала пробуем личным сообщением, а если ЛС недоступно
    (юзер не начинал диалог с ботом) — публикуем нейтральный `fallback_notice`
    (не сам `text`, чтобы не спалить содержимое); `sensitive=False` — публикуем text как есть.
    Публичный fallback пробрасывает остальные `kwargs` (например, `parse_mode`), но вырезает
    `reply_markup` -- клавиатура рассчитана на эфемерный контекст, публично её слать нельзя.
    Публичный fallback планирует автоудаление через `schedule_autodelete`, если передан `autodelete`.
    """
    if message.chat.type == ChatType.PRIVATE:
        return await bot.send_message(chat_id=message.chat.id, text=text, **kwargs)

    user_id = message.from_user.id
    reply_parameters = (
        ReplyParameters(ephemeral_message_id=message.ephemeral_message_id)
        if message.ephemeral_message_id is not None
        else None
    )

    try:
        return await bot.send_message(
            chat_id=message.chat.id,
            text=text,
            ephemeral_message_parameters=EphemeralMessageParameters(receiver_user_id=user_id),
            reply_parameters=reply_parameters,
            **kwargs,
        )
    except (TelegramBadRequest, TelegramForbiddenError):
        logger.debug("Ephemeral send failed in chat %d, falling back", message.chat.id)

    public_kwargs = {k: v for k, v in kwargs.items() if k != "reply_markup"}

    if sensitive:
        try:
            return await bot.send_message(chat_id=user_id, text=text, **kwargs)
        except (TelegramBadRequest, TelegramForbiddenError):
            logger.debug("DM fallback failed for user %d, posting neutral notice", user_id)
        sent = await safe_send_message(bot, message.chat.id, text=fallback_notice, **public_kwargs)
    else:
        sent = await safe_send_message(bot, message.chat.id, text=text, **public_kwargs)

    if sent and autodelete:
        autodelete_settings, msg_type = autodelete
        await schedule_autodelete(message.chat.id, sent.message_id, autodelete_settings, msg_type)

    return None if sensitive else sent


async def safe_delete_message(bot: Bot, chat_id: int, message_id: int) -> bool:
    """Удалить сообщение. Возвращает True если удалено, False если нет прав."""
    if await permissions.is_missing(chat_id, "can_delete_messages"):
        return False
    try:
        await bot.delete_message(chat_id, message_id)
        return True
    except TelegramBadRequest as e:
        perm = permissions.parse_missing_permission(str(e))
        if perm:
            await permissions.record_missing(chat_id, perm)
            return False
        raise


async def safe_restrict_member(bot: Bot, chat_id: int, user_id: int, **kwargs) -> bool:
    """Ограничить пользователя. Возвращает True если успешно."""
    if await permissions.is_missing(chat_id, "can_restrict_members"):
        return False
    try:
        await bot.restrict_chat_member(chat_id, user_id, **kwargs)
        return True
    except TelegramBadRequest as e:
        perm = permissions.parse_missing_permission(str(e))
        if perm:
            await permissions.record_missing(chat_id, perm)
            return False
        raise


async def safe_ban_member(bot: Bot, chat_id: int, user_id: int, **kwargs) -> bool:
    """Забанить пользователя. Возвращает True если успешно."""
    if await permissions.is_missing(chat_id, "can_restrict_members"):
        return False
    try:
        await bot.ban_chat_member(chat_id, user_id, **kwargs)
        return True
    except TelegramBadRequest as e:
        perm = permissions.parse_missing_permission(str(e))
        if perm:
            await permissions.record_missing(chat_id, perm)
            return False
        raise


async def safe_unban_member(bot: Bot, chat_id: int, user_id: int, **kwargs) -> bool:
    """Разбанить пользователя. Возвращает True если успешно."""
    if await permissions.is_missing(chat_id, "can_restrict_members"):
        return False
    try:
        await bot.unban_chat_member(chat_id, user_id, **kwargs)
        return True
    except TelegramBadRequest as e:
        perm = permissions.parse_missing_permission(str(e))
        if perm:
            await permissions.record_missing(chat_id, perm)
            return False
        raise


async def restore_captcha_permissions(bot: Bot, chat_id: int, user_id: int, session_id: int, attempt: int = 1) -> bool:
    try:
        await bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=full_permissions())
        return True
    except Exception as exc:
        logger.warning("Cannot restore permissions for user %d in %d (attempt %d): %s", user_id, chat_id, attempt, exc)
        if not isinstance(exc, (TelegramRetryAfter, TelegramNetworkError, TelegramServerError)):
            if isinstance(exc, (TelegramBadRequest, TelegramForbiddenError)):
                missing = permissions.parse_missing_permission(str(exc))
                if missing is None and any(
                    marker in str(exc).lower()
                    for marker in (
                        "chat_admin_required",
                        "bot_not_admin",
                        "not an administrator",
                        "administrator rights",
                    )
                ):
                    missing = "can_restrict_members"
                if missing:
                    try:
                        await permissions.record_missing(chat_id, missing)
                    except Exception:
                        logger.exception("Cannot cache missing permission %s in chat %d", missing, chat_id)
            return False
        if attempt >= 5:
            logger.error("Permission restoration exhausted for captcha session %d", session_id)
            return False
        delay = max(5 * 2 ** (attempt - 1), exc.retry_after if isinstance(exc, TelegramRetryAfter) else 0)
        try:
            await broker.publish(
                message={"chat_id": chat_id, "user_id": user_id, "session_id": session_id, "attempt": attempt + 1},
                exchange=delayed_exchange,
                routing_key="q.captcha.restore",
                headers={"x-delay": delay * 1000},
                persist=True,
            )
        except Exception:
            logger.exception("Cannot schedule permission restoration for captcha session %d", session_id)
        return False


async def delete_captcha_messages(
    bot: Bot, chat_id: int, user_id: int, message_id: int | None, ephemeral_message_id: int | None
) -> None:
    if ephemeral_message_id is not None:
        with suppress(Exception):
            await bot.delete_ephemeral_message(
                chat_id=chat_id, receiver_user_id=user_id, ephemeral_message_id=ephemeral_message_id
            )
    if message_id is not None:
        with suppress(Exception):
            await safe_delete_message(bot, chat_id, message_id)
