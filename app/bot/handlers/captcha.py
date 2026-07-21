import logging
from contextlib import suppress
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from fluentogram import TranslatorRunner
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.instance import bot
from app.core.broker import schedule_autodelete
from app.core.safe_telegram import full_permissions
from app.db.models.captcha_session import CaptchaSessionStatus, ChatCaptchaSession, claim_session
from app.db.models.chat import Chat
from app.db.models.user import User
from app.services.captcha_service import CaptchaResult, CaptchaService
from app.services.welcome_service import send_welcome_message

logger = logging.getLogger(__name__)

router = Router()


async def _get_pending_session(session: AsyncSession, chat_id: int, user_id: int) -> ChatCaptchaSession | None:
    """Найти PENDING-сессию капчи по чату/юзеру, ещё не истёкшую."""
    stmt = select(ChatCaptchaSession).where(
        ChatCaptchaSession.chat_id == chat_id,
        ChatCaptchaSession.user_id == user_id,
        ChatCaptchaSession.status == CaptchaSessionStatus.PENDING,
        ChatCaptchaSession.expires_at > datetime.now().astimezone(),
    )
    result = await session.execute(stmt)
    return result.scalars().first()


@router.callback_query(F.data.startswith("cap:"))
async def on_captcha_callback(callback: CallbackQuery, session: AsyncSession, i18n: TranslatorRunner) -> None:
    """Обработка нажатия на кнопку капчи."""
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Invalid data")
        return

    try:
        target_user_id = int(parts[1])
    except ValueError:
        await callback.answer("Invalid user id")
        return

    code = parts[2]

    if callback.from_user.id != target_user_id:
        await callback.answer(i18n.captcha.foreign(), show_alert=True)
        return

    chat = callback.message.chat
    user = callback.from_user

    result = await CaptchaService.verify_attempt(chat.id, user.id, code)

    if result == CaptchaResult.SUCCESS:
        await _handle_success(callback, session, i18n)
    elif result == CaptchaResult.RETRY:
        await _handle_retry(callback, session, i18n)
    elif result == CaptchaResult.FAIL:
        await _handle_fail(callback, session, i18n)


async def _handle_success(callback: CallbackQuery, session: AsyncSession, i18n: TranslatorRunner) -> None:
    chat = callback.message.chat
    user = callback.from_user

    captcha_session = await _get_pending_session(session, chat.id, user.id)

    claimed = bool(captcha_session) and await claim_session(session, captcha_session.id, CaptchaSessionStatus.PASSED)
    if not claimed:
        await callback.answer()
        return

    db_user = await session.get(User, user.id)
    if db_user:
        db_user.has_passed_captcha = True

    await session.commit()

    try:
        await bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=user.id,
            permissions=full_permissions(),
        )
    except Exception as e:
        logger.error(f"Failed to unmute user {user.id}: {e}")

    is_ephemeral = captcha_session.ephemeral_message_id is not None

    if is_ephemeral:
        with suppress(Exception):
            await bot.delete_ephemeral_message(
                chat_id=chat.id,
                receiver_user_id=user.id,
                ephemeral_message_id=captcha_session.ephemeral_message_id,
            )
    else:
        with suppress(Exception):
            await callback.message.delete()

    db_chat = await session.get(Chat, chat.id)

    sent_welcome = False
    if db_chat:
        sent_welcome = await send_welcome_message(bot, session, chat, user, db_chat)

    if not sent_welcome:
        msg_text = i18n.captcha.success()
        sent_msg = None

        if is_ephemeral:
            try:
                sent_msg = await bot.send_message(
                    chat_id=chat.id,
                    text=msg_text,
                    parse_mode="HTML",
                    receiver_user_id=user.id,
                )
            except (TelegramBadRequest, TelegramForbiddenError):
                logger.debug(f"Ephemeral success message failed in {chat.id}, falling back to public")

        if sent_msg is None:
            try:
                sent_msg = await bot.send_message(chat_id=chat.id, text=msg_text, parse_mode="HTML")
                if db_chat:
                    await schedule_autodelete(
                        chat.id, sent_msg.message_id, db_chat.autodelete_settings, "captcha_success"
                    )
            except Exception as e:
                logger.error(f"Failed to send success message: {e}")


async def _handle_retry(callback: CallbackQuery, session: AsyncSession, i18n: TranslatorRunner) -> None:
    chat = callback.message.chat
    user = callback.from_user

    session_data = await CaptchaService.get_session(chat.id, user.id)
    attempts = session_data.attempts_left if session_data else 0

    await callback.answer(i18n.captcha.retry(attempts=attempts), show_alert=True)

    captcha_data = await CaptchaService.regenerate_session(chat.id, user.id)
    if not captcha_data:
        return

    buttons = [
        InlineKeyboardButton(text=btn.emoji, callback_data=f"cap:{user.id}:{btn.code}", style=btn.style)
        for btn in captcha_data.buttons
    ]

    keyboard_rows = [buttons[i : i + 4] for i in range(0, len(buttons), 4)]
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    captcha_colors = {
        "danger": i18n.captcha.color.danger(),
        "success": i18n.captcha.color.success(),
        "primary": i18n.captcha.color.primary(),
    }
    color = captcha_colors[captcha_data.target_style]
    msg_text = i18n.captcha.emoji(user=user.mention_html(), emoji=captcha_data.target_emoji, color=color)

    captcha_session = await _get_pending_session(session, chat.id, user.id)

    if captcha_session and captcha_session.ephemeral_message_id is not None:
        with suppress(TelegramBadRequest, TelegramForbiddenError):
            await bot.edit_ephemeral_message_text(
                chat_id=chat.id,
                receiver_user_id=user.id,
                ephemeral_message_id=captcha_session.ephemeral_message_id,
                text=msg_text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
    else:
        with suppress(TelegramBadRequest):
            await callback.message.edit_text(text=msg_text, reply_markup=keyboard, parse_mode="HTML")


async def _handle_fail(callback: CallbackQuery, session: AsyncSession, i18n: TranslatorRunner) -> None:
    chat = callback.message.chat
    user = callback.from_user

    captcha_session = await _get_pending_session(session, chat.id, user.id)

    claimed = bool(captcha_session) and await claim_session(session, captcha_session.id, CaptchaSessionStatus.DECLINED)
    if not claimed:
        await callback.answer()
        return

    db_chat = await session.get(Chat, chat.id)
    ban_duration = db_chat.captcha_ban_duration if db_chat else 259200

    await callback.answer(i18n.captcha.fail(), show_alert=True)

    try:
        await bot.ban_chat_member(
            chat_id=chat.id,
            user_id=user.id,
            until_date=timedelta(seconds=ban_duration),
        )
    except Exception as e:
        logger.error(f"Failed to ban user {user.id}: {e}")

    if captcha_session.ephemeral_message_id is not None:
        with suppress(Exception):
            await bot.delete_ephemeral_message(
                chat_id=chat.id,
                receiver_user_id=user.id,
                ephemeral_message_id=captcha_session.ephemeral_message_id,
            )
    else:
        with suppress(Exception):
            await callback.message.delete()
