import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from fluentogram import TranslatorRunner
from sqlalchemy.ext.asyncio import AsyncSession
from yarl import URL

from app.bot.handlers.creation_private import parse_deep_link, start_from_deep_link
from app.bot.instance import bot
from app.core.config import settings
from app.db.models.captcha_session import ChatCaptchaSession

logger = logging.getLogger(__name__)

router = Router()


@router.message(CommandStart(), F.chat.type == "private")
async def start_command(
    message: Message,
    i18n: TranslatorRunner,
    session: AsyncSession,
    state: FSMContext | None = None,
) -> None:
    """
    Обработчик команды /start в личных сообщениях.
    Поддерживает deep link для капчи: /start captcha_{session_id}
    Поддерживает deep link для создания триггера: /start newtrigger_{chat_id}
    """
    args = message.text.split(maxsplit=1)

    if len(args) > 1 and state is not None:
        chat_id = parse_deep_link(args[1])
        if chat_id is not None:
            await start_from_deep_link(
                message,
                chat_id=chat_id,
                state=state,
                session=session,
                bot=message.bot,
                i18n=i18n,
            )
            return

    if len(args) > 1 and args[1].startswith("captcha_"):
        try:
            session_id = int(args[1].replace("captcha_", ""))
            captcha_session = await session.get(ChatCaptchaSession, session_id)

            if not captcha_session:
                await message.answer(i18n.captcha.missing(), parse_mode="HTML")
                return

            if captcha_session.user_id != message.from_user.id:
                await message.answer(i18n.captcha.wrong.user(), parse_mode="HTML")
                return

            if captcha_session.is_completed:
                await message.answer(i18n.captcha.already.completed(), parse_mode="HTML")
                return

            if captcha_session.expires_at < datetime.now().astimezone():
                await message.answer(i18n.captcha.expired(), parse_mode="HTML")
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
                            text=i18n.btn.verify(),
                            web_app=WebAppInfo(url=str(url)),
                        )
                    ]
                ]
            )

            await message.answer(
                i18n.captcha.open.webapp(),
                reply_markup=keyboard,
                parse_mode="HTML",
            )

        except (ValueError, TypeError):
            await message.answer(i18n.captcha.invalid.link(), parse_mode="HTML")
    elif len(args) > 1 and args[1].startswith("settings_"):
        try:
            chat_id = int(args[1].replace("settings_", ""))

            try:
                member = await bot.get_chat_member(chat_id, message.from_user.id)
                if member.status not in ("administrator", "creator"):
                    await message.answer(i18n.settings.no.admin(), parse_mode="HTML")
                    return
            except Exception as e:
                logger.error(f"Failed to check chat member for settings deep link: {e}")
                await message.answer(i18n.settings.chat.missing(), parse_mode="HTML")
                return

            url = URL(settings.WEBAPP_URL)
            if settings.URL_PREFIX:
                url = url / settings.URL_PREFIX.strip("/")
            url = url / "webapp"
            url = url.with_fragment(f"/settings/{chat_id}")

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=i18n.settings.open.webapp(),
                            web_app=WebAppInfo(url=str(url)),
                        )
                    ]
                ]
            )

            await message.answer(
                i18n.settings.webapp.sent(),
                reply_markup=keyboard,
                parse_mode="HTML",
            )

        except (ValueError, TypeError):
            await message.answer(i18n.start.message(version=settings.BOT_VERSION), parse_mode="HTML")
    else:
        await message.answer(i18n.start.message(version=settings.BOT_VERSION), parse_mode="HTML")
