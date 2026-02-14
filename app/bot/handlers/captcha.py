import logging
from contextlib import suppress
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from fluentogram import TranslatorRunner
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.instance import bot
from app.core.broker import broker, delayed_exchange
from app.db.models.captcha_session import ChatCaptchaSession
from app.db.models.chat import Chat
from app.db.models.user import User
from app.services.captcha_service import CaptchaResult, CaptchaService
from app.services.welcome_service import send_welcome_message

logger = logging.getLogger(__name__)

router = Router()


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
        await callback.answer(i18n.get("captcha-not-for-you"), show_alert=True)
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

    stmt = select(ChatCaptchaSession).where(
        ChatCaptchaSession.chat_id == chat.id,
        ChatCaptchaSession.user_id == user.id,
        ChatCaptchaSession.is_completed == False,  # noqa: E712
        ChatCaptchaSession.expires_at > datetime.now().astimezone(),
    )
    result = await session.execute(stmt)
    captcha_session = result.scalars().first()

    if captcha_session:
        captcha_session.is_completed = True

    db_user = await session.get(User, user.id)
    if db_user:
        db_user.has_passed_captcha = True

    await session.commit()

    try:
        await bot.restrict_chat_member(
            chat_id=chat.id,
            user_id=user.id,
            permissions=ChatPermissions(
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
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False,
                can_manage_topics=False,
            ),
        )
    except Exception as e:
        logger.error(f"Failed to unmute user {user.id}: {e}")

    with suppress(Exception):
        await callback.message.delete()

    db_chat = await session.get(Chat, chat.id)

    sent_welcome = False
    if db_chat:
        sent_welcome = await send_welcome_message(bot, session, chat, user, db_chat)

    if not sent_welcome:
        try:
            msg_text = i18n.get("captcha-success")
            sent_msg = await bot.send_message(chat_id=chat.id, text=msg_text, parse_mode="HTML")

            await broker.publish(
                message={"chat_id": chat.id, "message_id": sent_msg.message_id},
                exchange=delayed_exchange,
                routing_key="q.messages.delete",
                headers={"x-delay": 10000},
            )
        except Exception as e:
            logger.error(f"Failed to send success message: {e}")


async def _handle_retry(callback: CallbackQuery, session: AsyncSession, i18n: TranslatorRunner) -> None:
    chat = callback.message.chat
    user = callback.from_user

    session_data = await CaptchaService.get_session(chat.id, user.id)
    attempts = session_data.attempts_left if session_data else 0

    await callback.answer(i18n.get("captcha-retry", attempts=attempts), show_alert=True)

    captcha_data = await CaptchaService.create_session(chat.id, user.id)

    buttons = [
        InlineKeyboardButton(text=btn.emoji, callback_data=f"cap:{user.id}:{btn.code}", style=btn.style)
        for btn in captcha_data.buttons
    ]

    keyboard_rows = [buttons[i : i + 4] for i in range(0, len(buttons), 4)]
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

    color = i18n.get(f"captcha-color-{captcha_data.target_style}")
    msg_text = i18n.get("captcha-emoji", user=user.mention_html(), emoji=captcha_data.target_emoji, color=color)

    with suppress(TelegramBadRequest):
        await callback.message.edit_text(text=msg_text, reply_markup=keyboard, parse_mode="HTML")


async def _handle_fail(callback: CallbackQuery, session: AsyncSession, i18n: TranslatorRunner) -> None:
    chat = callback.message.chat
    user = callback.from_user

    await callback.answer(i18n.get("captcha-fail"), show_alert=True)

    try:
        await bot.ban_chat_member(
            chat_id=chat.id,
            user_id=user.id,
            until_date=timedelta(minutes=1),
        )
        await bot.unban_chat_member(chat_id=chat.id, user_id=user.id)
    except Exception as e:
        logger.error(f"Failed to kick user {user.id}: {e}")

    with suppress(Exception):
        await callback.message.delete()
