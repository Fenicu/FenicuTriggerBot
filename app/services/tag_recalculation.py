import asyncio
import logging

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.bot.instance import bot
from app.core.database import engine
from app.db.models.chat import Chat
from app.db.models.user_chat import UserChat
from app.services.reputation_service import calculate_level, get_level_name, get_thresholds
from app.services.tag_service import SetChatMemberTag

logger = logging.getLogger(__name__)

async_session = async_sessionmaker(engine, expire_on_commit=False)

# Ошибки, при которых пользователь помечается как неактивный
_DEACTIVATE_MESSAGES = frozenset(
    {
        "USER_NOT_PARTICIPANT",
        "PARTICIPANT_ID_INVALID",
        "user is deactivated",
    }
)

# Ошибки, которые нужно просто пропустить (не деактивируя)
_SKIP_MESSAGES = frozenset(
    {
        "CHAT_CREATOR_REQUIRED",
    }
)

# Задержка между вызовами Telegram API (секунды)
_BASE_DELAY = 1.0
# Дополнительный запас к retry_after от Telegram
_RETRY_EXTRA = 3.0
# Максимальное число попыток при flood control
_MAX_RETRIES = 2


def _should_deactivate(message: str) -> bool:
    """Проверить, нужно ли деактивировать пользователя по тексту ошибки."""
    return any(marker in message for marker in _DEACTIVATE_MESSAGES)


def _should_skip(message: str) -> bool:
    """Проверить, нужно ли пропустить пользователя без деактивации."""
    return any(marker in message for marker in _SKIP_MESSAGES)


async def recalculate_chat_tags(chat_id: int) -> None:
    """Пересчитать уровни и теги всех пользователей чата."""
    async with async_session() as session:
        chat = await session.get(Chat, chat_id)
        if not chat or not chat.tags_enabled:
            return

        thresholds = get_thresholds(chat)

        stmt = select(UserChat).where(
            UserChat.chat_id == chat_id,
            UserChat.is_active.is_(True),
        )
        result = await session.execute(stmt)
        user_chats = result.scalars().all()

        updated = 0
        skipped = 0
        deactivated = 0
        for user_chat in user_chats:
            if user_chat.tag_is_manual:
                continue

            new_level = calculate_level(user_chat.reputation_score, thresholds)
            new_tag = get_level_name(new_level, chat)

            if new_level == user_chat.reputation_level and new_tag == user_chat.tag:
                continue

            success = await _set_tag_with_retry(chat_id, user_chat, new_tag or "")
            if success is True:
                # Обновляем ORM только после успешного вызова Telegram API
                user_chat.reputation_level = new_level
                user_chat.tag = new_tag or None
                updated += 1
            elif success is None:
                # Пользователь невалиден — деактивируем запись
                user_chat.is_active = False
                deactivated += 1
            else:
                skipped += 1

            await asyncio.sleep(_BASE_DELAY)

        await session.commit()
        logger.info(
            "Recalculated tags for chat %d: %d updated, %d skipped, %d deactivated (out of %d)",
            chat_id,
            updated,
            skipped,
            deactivated,
            len(user_chats),
        )


async def _set_tag_with_retry(
    chat_id: int,
    user_chat: UserChat,
    tag: str,
) -> bool | None:
    """Установить тег с обработкой ошибок.

    Returns:
        True — успешно обновлено
        False — пропущено (creator, прочие некритичные ошибки)
        None — пользователь невалиден, нужно деактивировать
    """
    for attempt in range(_MAX_RETRIES + 1):
        try:
            await bot(
                SetChatMemberTag(
                    chat_id=chat_id,
                    user_id=user_chat.user_id,
                    tag=tag,
                )
            )
            return True

        except TelegramRetryAfter as e:
            if attempt < _MAX_RETRIES:
                wait = e.retry_after + _RETRY_EXTRA
                logger.info(
                    "Rate limited on tag update for user %d in chat %d, waiting %.0fs (attempt %d/%d)",
                    user_chat.user_id,
                    chat_id,
                    wait,
                    attempt + 1,
                    _MAX_RETRIES + 1,
                )
                await asyncio.sleep(wait)
            else:
                logger.warning(
                    "Rate limit exhausted for user %d in chat %d after %d attempts",
                    user_chat.user_id,
                    chat_id,
                    _MAX_RETRIES + 1,
                )
                return False

        except TelegramForbiddenError as e:
            if _should_deactivate(str(e)):
                logger.debug(
                    "Deactivating user %d in chat %d: %s",
                    user_chat.user_id,
                    chat_id,
                    e,
                )
                return None
            logger.warning(
                "Forbidden error for user %d in chat %d: %s",
                user_chat.user_id,
                chat_id,
                e,
            )
            return False

        except TelegramBadRequest as e:
            msg = str(e)
            if _should_deactivate(msg):
                logger.debug(
                    "Deactivating user %d in chat %d: %s",
                    user_chat.user_id,
                    chat_id,
                    e,
                )
                return None
            if _should_skip(msg):
                return False
            logger.warning(
                "Bad request for user %d in chat %d: %s",
                user_chat.user_id,
                chat_id,
                e,
            )
            return False

        except Exception as e:
            logger.warning(
                "Unexpected error updating tag for user %d in chat %d: %s",
                user_chat.user_id,
                chat_id,
                e,
            )
            return False

    return False
