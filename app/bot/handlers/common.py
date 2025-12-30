from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from fluentogram import TranslatorRunner

from app.core.config import settings

router = Router()


@router.message(CommandStart(), F.chat.type == "private")
async def start_command(message: Message, i18n: TranslatorRunner) -> None:
    """Обработчик команды /start в личных сообщениях."""
    await message.answer(i18n.get("start-message", version=settings.BOT_VERSION), parse_mode="HTML")
