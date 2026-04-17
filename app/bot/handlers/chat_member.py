import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import (
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from fluentogram import TranslatorRunner
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.instance import bot
from app.core.broker import broker, delayed_exchange, schedule_autodelete
from app.core.safe_telegram import (
    full_permissions,
    full_restrictions,
    safe_ban_member,
    safe_restrict_member,
    safe_send_message,
)
from app.db.models.captcha_session import ChatCaptchaSession
from app.db.models.user_chat import UserChat
from app.services.captcha_service import CaptchaService
from app.services.chat_service import get_or_create_chat
from app.services.gban_service import GbanService
from app.services.user_service import get_or_create_user
from app.services.welcome_service import send_welcome_message

logger = logging.getLogger(__name__)

router = Router()


@router.chat_member()
async def on_chat_member_update(event: ChatMemberUpdated, session: AsyncSession, i18n: TranslatorRunner) -> None:
    """Обработчик изменений статуса участника чата."""
    user = event.new_chat_member.user
    chat = event.chat

    if chat.type == "private":
        return

    db_user = await get_or_create_user(
        session=session,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        language_code=user.language_code,
        is_premium=user.is_premium,
    )

    photo_id = None
    if chat.photo:
        photo_id = chat.photo.big_file_id

    db_chat = await get_or_create_chat(
        session=session,
        chat_id=chat.id,
        title=chat.title,
        username=chat.username,
        type=chat.type,
        description=chat.description,
        invite_link=chat.invite_link,
        photo_id=photo_id,
    )

    new_status = event.new_chat_member.status
    old_status = event.old_chat_member.status

    is_active = new_status in ("member", "administrator", "creator", "restricted")
    is_admin = new_status in ("administrator", "creator")

    stmt = (
        insert(UserChat)
        .values(user_id=user.id, chat_id=chat.id, is_active=is_active, is_admin=is_admin)
        .on_conflict_do_update(
            index_elements=[UserChat.user_id, UserChat.chat_id],
            set_={"is_active": is_active, "is_admin": is_admin, "updated_at": func.now()},
        )
    )
    await session.execute(stmt)
    await session.commit()
    logger.debug(f"Updated UserChat {user.id} in {chat.id}: active={is_active}, admin={is_admin}")

    is_joining = old_status in ("left", "kicked") and new_status in ("member", "restricted")

    if not is_joining:
        return

    if db_chat.gban_enabled and await GbanService.is_banned(user.id):
        try:
            banned = await safe_ban_member(bot, chat.id, user.id)
            if not banned:
                logger.warning(f"Cannot gban user {user.id} in {chat.id} (no restrict rights)")
                return
            sent = await safe_send_message(
                bot, chat.id,
                text=i18n.gban.user.banned(user=user.mention_html()),
                parse_mode="HTML",
            )
            if sent:
                await schedule_autodelete(chat.id, sent.message_id, db_chat.autodelete_settings, "gban")
            return
        except Exception as e:
            logger.error(f"Failed to gban user {user.id} in {chat.id}: {e}")

    needs_captcha = False
    if db_chat.captcha_enabled and not (
        is_admin or db_user.is_bot_moderator or db_user.is_trusted or db_user.has_passed_captcha
    ):
        needs_captcha = True

    if needs_captcha:
        restricted = await safe_restrict_member(
            bot, chat.id, user.id,
            permissions=full_restrictions(),
        )
        if not restricted:
            logger.warning(f"Cannot restrict user {user.id} in {chat.id} (no restrict rights)")

        expires_at = datetime.now().astimezone() + timedelta(seconds=db_chat.captcha_timeout)
        captcha_session = ChatCaptchaSession(
            chat_id=chat.id,
            user_id=user.id,
            expires_at=expires_at,
            message_id=0,
        )
        session.add(captcha_session)
        await session.flush()

        keyboard = None
        msg_text = ""

        if db_chat.captcha_type == "emoji":
            captcha_data = await CaptchaService.create_session(
                chat.id, user.id, session_ttl=db_chat.captcha_timeout, max_attempts=db_chat.captcha_max_attempts
            )

            buttons = [
                InlineKeyboardButton(
                    text=btn.emoji,
                    callback_data=f"cap:{user.id}:{btn.code}",
                    style=btn.style,
                )
                for btn in captcha_data.buttons
            ]

            # 4x4 grid
            keyboard_rows = [buttons[i : i + 4] for i in range(0, len(buttons), 4)]
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

            captcha_colors = {
                "danger": i18n.captcha.color.danger(),
                "success": i18n.captcha.color.success(),
                "primary": i18n.captcha.color.primary(),
            }
            color = captcha_colors[captcha_data.target_style]
            msg_text = i18n.captcha.emoji(user=user.mention_html(), emoji=captcha_data.target_emoji, color=color)

        else:
            bot_info = await bot.get_me()
            payload = f"captcha_{captcha_session.id}"
            deep_link = f"https://t.me/{bot_info.username}?start={payload}"

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=i18n.btn.verify(),
                            url=deep_link,
                        )
                    ]
                ]
            )

            msg_text = i18n.captcha.verify(user=user.mention_html())

        async def _send_captcha() -> bool:
            sent_msg = await safe_send_message(
                bot, chat.id,
                text=msg_text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            if not sent_msg:
                return False
            captcha_session.message_id = sent_msg.message_id
            await session.commit()
            await broker.publish(
                message={"chat_id": chat.id, "user_id": user.id, "session_id": captcha_session.id},
                exchange=delayed_exchange,
                routing_key="q.captcha.kick",
                headers={"x-delay": (db_chat.captcha_timeout + 1) * 1000},
            )
            return True

        sent_ok = False
        try:
            sent_ok = await _send_captcha()
        except TelegramRetryAfter as e:
            logger.warning(f"Flood control sending captcha in {chat.id}, retry in {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            try:
                sent_ok = await _send_captcha()
            except Exception as retry_err:
                logger.error(f"Failed to send captcha after retry in {chat.id}: {retry_err}")
        except Exception as e:
            logger.error(f"Failed to send captcha message: {e}")

        if not sent_ok:
            # Не удалось отправить капчу — снимаем ограничения, чтобы пользователь не застрял навечно
            unrestricted = await safe_restrict_member(
                bot, chat.id, user.id,
                permissions=full_permissions(),
            )
            if unrestricted:
                logger.info(f"Unrestricted user {user.id} in {chat.id} after captcha send failure")
            else:
                logger.error(f"Failed to unrestrict user {user.id} in {chat.id} (no restrict rights)")

        return

    await send_welcome_message(bot, session, chat, user, db_chat)
