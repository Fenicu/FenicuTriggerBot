from datetime import datetime

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from fluentogram import TranslatorRunner
from sqlalchemy.ext.asyncio import AsyncSession
from yarl import URL

from app.core.config import settings
from app.db.models.captcha_session import ChatCaptchaSession

router = Router()


@router.message(CommandStart(), F.chat.type == "private")
async def start_command(message: Message, i18n: TranslatorRunner, session: AsyncSession) -> None:
    """
    Обработчик команды /start в личных сообщениях.
    Поддерживает deep link для капчи: /start captcha_{session_id}
    """
    args = message.text.split(maxsplit=1)

    if len(args) > 1 and args[1].startswith("captcha_"):
        try:
            session_id = int(args[1].replace("captcha_", ""))
            captcha_session = await session.get(ChatCaptchaSession, session_id)

            if not captcha_session:
                await message.answer(i18n.get("captcha-not-found"), parse_mode="HTML")
                return

            if captcha_session.user_id != message.from_user.id:
                await message.answer(i18n.get("captcha-wrong-user"), parse_mode="HTML")
                return

            if captcha_session.is_completed:
                await message.answer(i18n.get("captcha-already-completed"), parse_mode="HTML")
                return

            if captcha_session.expires_at < datetime.now().astimezone():
                await message.answer(i18n.get("captcha-expired"), parse_mode="HTML")
                return

            url = URL(settings.WEBAPP_URL)
            if settings.URL_PREFIX:
                url = url / settings.URL_PREFIX.strip("/")
            url = url / "webapp"

            url = url.with_fragment("/captcha")

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=i18n.get("btn-verify"),
                            web_app=WebAppInfo(url=str(url)),
                        )
                    ]
                ]
            )

            await message.answer(
                i18n.get("captcha-open-webapp"),
                reply_markup=keyboard,
                parse_mode="HTML",
            )

        except (ValueError, TypeError):
            await message.answer(i18n.get("captcha-invalid-link"), parse_mode="HTML")
    else:
        await message.answer(i18n.get("start-message", version=settings.BOT_VERSION), parse_mode="HTML")
