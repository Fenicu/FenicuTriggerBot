import logging
from datetime import datetime, timedelta

from aiogram import Router
from aiogram.types import ChatMemberUpdated
from fluentogram import TranslatorRunner
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.instance import bot
from app.core import permissions
from app.core.broker import broker, delayed_exchange, schedule_autodelete
from app.core.safe_telegram import (
    delete_captcha_messages,
    safe_ban_member,
    safe_send_message,
)
from app.db.models.captcha_session import CaptchaSessionKind, CaptchaSessionStatus, ChatCaptchaSession, claim_session
from app.db.models.user_chat import UserChat, has_passed_chat_captcha, mark_chat_captcha_passed
from app.services.captcha_service import (
    CaptchaService,
    deliver_chat_captcha,
)
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

    if old_status == "restricted" and new_status == "member":
        pending = (
            await session.scalars(
                select(ChatCaptchaSession).where(
                    ChatCaptchaSession.chat_id == chat.id,
                    ChatCaptchaSession.user_id == user.id,
                    ChatCaptchaSession.kind == CaptchaSessionKind.CHAT,
                    ChatCaptchaSession.status == CaptchaSessionStatus.PENDING,
                )
            )
        ).all()
        for captcha in pending:
            if await claim_session(session, captcha.id, CaptchaSessionStatus.PASSED):
                await mark_chat_captcha_passed(session, chat.id, user.id)
                await session.commit()
                await delete_captcha_messages(bot, chat.id, user.id, captcha.message_id, captcha.ephemeral_message_id)
        return

    if not is_joining:
        return

    if db_chat.gban_enabled and await GbanService.is_banned(user.id):
        try:
            banned = await safe_ban_member(bot, chat.id, user.id)
            if not banned:
                logger.warning(f"Cannot gban user {user.id} in {chat.id} (no restrict rights)")
                return
            sent = await safe_send_message(
                bot,
                chat.id,
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
        is_admin
        or db_user.is_bot_moderator
        or db_user.is_trusted
        or await has_passed_chat_captcha(session, chat.id, user.id)
    ):
        needs_captcha = True

    if needs_captcha:
        captcha_session = ChatCaptchaSession(
            chat_id=chat.id,
            user_id=user.id,
            expires_at=datetime.now().astimezone() + timedelta(seconds=db_chat.captcha_timeout),
        )
        session.add(captcha_session)
        if db_chat.captcha_type == "emoji":
            await CaptchaService.create_session(
                chat.id, user.id, session_ttl=db_chat.captcha_timeout, max_attempts=db_chat.captcha_max_attempts
            )
        await session.commit()
        if not await permissions.is_missing(chat.id, "can_send_messages"):
            await broker.publish(
                message={"chat_id": chat.id, "user_id": user.id, "session_id": captcha_session.id},
                exchange=delayed_exchange,
                routing_key="q.captcha.kick",
                headers={"x-delay": (db_chat.captcha_timeout + 1) * 1000},
                persist=True,
            )
        await deliver_chat_captcha(bot, session, captcha_session, db_chat, i18n, user.mention_html(), broker)
        return

    await send_welcome_message(bot, session, chat, user, db_chat)
