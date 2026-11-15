import contextlib
import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter
from aiogram.types import Message
from fluentogram import TranslatorRunner

from app.core import permissions
from app.core.config import settings as bot_settings
from app.core.safe_telegram import ephemeral_answer
from app.db.models.chat import Chat
from app.db.models.user import User
from app.services.audit_service import check_section_access

logger = logging.getLogger(__name__)


def is_settings_creator(member_status: str | None, user: User | None = None) -> bool:
    """Создатель чата или staff бота — те, кому доступны заблокированные секции.

    Правило повторяет API (require_chat_admin): BOT_ADMINS и бот-модераторы
    приравнены к создателю чата.
    """
    if user is not None and (getattr(user, "is_bot_moderator", False) or user.id in bot_settings.BOT_ADMINS):
        return True
    return member_status == "creator"


def locked_fields(chat: Chat, update_data: dict, is_creator: bool) -> list[str]:
    """Поля из секций, заблокированных создателем чата для остальных админов."""
    return check_section_access(chat, update_data, is_creator)


def section_is_locked(chat: Chat, section: str, is_creator: bool) -> bool:
    """Заблокирована ли секция для не-создателя."""
    if is_creator:
        return False
    return section in (chat.settings_locked_sections or [])


class IsModerationEnabled(BaseFilter):
    """
    Фильтр проверяет, включен ли модуль модерации в чате.
    Если выключен - просто игнорирует апдейт (silent failure).
    """

    async def __call__(self, message: Message, db_chat: Chat | None = None) -> bool:
        if not db_chat:
            return False
        return db_chat.module_moderation


class HasBotRights(BaseFilter):
    """
    Проверяет права администратора у бота.
    Если прав нет - отправляет сообщение об ошибке.
    """

    async def __call__(self, message: Message, i18n: TranslatorRunner) -> bool:
        chat_id = message.chat.id

        if await permissions.is_missing(chat_id, "can_send_messages"):
            return False

        bot_member = await message.chat.get_member(message.bot.id)
        if bot_member.status != "administrator":
            try:
                await ephemeral_answer(
                    message.bot, message, i18n.mod.error.no.rights(), sensitive=False, parse_mode="HTML"
                )
            except TelegramBadRequest as e:
                perm = permissions.parse_missing_permission(str(e))
                if perm:
                    await permissions.record_missing(chat_id, perm)
                logger.warning("No rights to send messages in chat %s", chat_id)
            return False
        return True


class HasUserRights(BaseFilter):
    """
    Проверяет, что у пользователя есть право ограничивать участников.
    Создатель чата проходит всегда, админ — только с can_restrict_members.
    Если прав нет - отправляет сообщение об ошибке.
    """

    async def __call__(self, message: Message, i18n: TranslatorRunner) -> bool:
        # Анонимный администратор пишет от имени самого чата.
        if message.sender_chat and message.sender_chat.id == message.chat.id:
            return True

        if not message.from_user:
            return False

        try:
            user_member = await message.chat.get_member(message.from_user.id)
        except TelegramBadRequest:
            logger.warning("Invalid participant ID %s in chat %s", message.from_user.id, message.chat.id)
            return False

        if user_member.status == "creator":
            return True
        if user_member.status == "administrator" and getattr(user_member, "can_restrict_members", False):
            return True

        with contextlib.suppress(TelegramBadRequest):
            await ephemeral_answer(message.bot, message, i18n.mod.error.no.rights(), sensitive=False, parse_mode="HTML")
        return False
