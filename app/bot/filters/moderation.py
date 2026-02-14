from aiogram.filters import BaseFilter
from aiogram.types import Message
from fluentogram import TranslatorRunner

from app.db.models.chat import Chat


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
        bot_member = await message.chat.get_member(message.bot.id)
        if bot_member.status != "administrator":
            await message.answer(i18n.mod.error.no.rights(), parse_mode="HTML")
            return False
        return True


class HasUserRights(BaseFilter):
    """
    Проверяет права администратора у пользователя.
    Если прав нет - отправляет сообщение об ошибке.
    """

    async def __call__(self, message: Message, i18n: TranslatorRunner) -> bool:
        if not message.from_user:
            return False

        user_member = await message.chat.get_member(message.from_user.id)
        if user_member.status not in ("administrator", "creator"):
            await message.answer(i18n.mod.error.no.rights(), parse_mode="HTML")
            return False
        return True
