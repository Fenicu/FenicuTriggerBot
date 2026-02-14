import logging
from datetime import datetime, timedelta

from aiogram import Router
from aiogram.types import (
    ChatMemberUpdated,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from fluentogram import TranslatorRunner
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.instance import bot
from app.core.broker import broker, delayed_exchange
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

    user_chat = await session.get(UserChat, (user.id, chat.id))
    if not user_chat:
        user_chat = UserChat(
            user_id=user.id,
            chat_id=chat.id,
            is_active=is_active,
            is_admin=is_admin,
        )
        session.add(user_chat)
    else:
        user_chat.is_active = is_active
        user_chat.is_admin = is_admin
        user_chat.updated_at = datetime.now().astimezone()

    await session.commit()
    logger.info(f"Updated UserChat {user.id} in {chat.id}: active={is_active}, admin={is_admin}")

    is_joining = old_status in ("left", "kicked") and new_status in ("member", "restricted")

    if not is_joining:
        return

    if db_chat.gban_enabled and await GbanService.is_banned(user.id):
        try:
            await bot.ban_chat_member(chat.id, user.id)
            await bot.send_message(
                chat.id,
                i18n.get("gban-user-banned", user=user.mention_html()),
                parse_mode="HTML",
            )
            return
        except Exception as e:
            logger.error(f"Failed to gban user {user.id} in {chat.id}: {e}")

    needs_captcha = False
    if db_chat.captcha_enabled and not (
        is_admin or db_user.is_bot_moderator or db_user.is_trusted or db_user.has_passed_captcha
    ):
        needs_captcha = True

    if needs_captcha:
        try:
            await bot.restrict_chat_member(
                chat_id=chat.id,
                user_id=user.id,
                permissions=ChatPermissions(
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
                    can_change_info=False,
                    can_invite_users=False,
                    can_pin_messages=False,
                    can_manage_topics=False,
                ),
            )
        except Exception as e:
            logger.error(f"Failed to restrict user {user.id} in {chat.id}: {e}")

        expires_at = datetime.now().astimezone() + timedelta(minutes=5)
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
            captcha_data = await CaptchaService.create_session(chat.id, user.id)

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

            color = i18n.get(f"captcha-color-{captcha_data.target_style}")
            msg_text = i18n.get("captcha-emoji", user=user.mention_html(), emoji=captcha_data.target_emoji, color=color)

        else:
            bot_info = await bot.get_me()
            payload = f"captcha_{captcha_session.id}"
            deep_link = f"https://t.me/{bot_info.username}?start={payload}"

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=i18n.get("btn-verify"),
                            url=deep_link,
                        )
                    ]
                ]
            )

            msg_text = i18n.get("captcha-verify", user=user.mention_html())

        try:
            sent_msg = await bot.send_message(
                chat_id=chat.id,
                text=msg_text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )

            captcha_session.message_id = sent_msg.message_id
            await session.commit()

            await broker.publish(
                message={"chat_id": chat.id, "user_id": user.id, "session_id": captcha_session.id},
                exchange=delayed_exchange,
                routing_key="q.captcha.kick",
                headers={"x-delay": 301000},
            )
        except Exception as e:
            logger.error(f"Failed to send captcha message: {e}")

        return

    await send_welcome_message(bot, session, chat, user, db_chat)
