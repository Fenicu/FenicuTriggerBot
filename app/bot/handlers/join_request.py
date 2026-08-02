import logging
import secrets
from datetime import datetime, timedelta

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.types import ChatJoinRequest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.instance import bot
from app.core.broker import broker, delayed_exchange
from app.core.safe_telegram import safe_ban_member
from app.db.models.captcha_session import (
    CaptchaSessionKind,
    CaptchaSessionStatus,
    ChatCaptchaSession,
    claim_session,
)
from app.db.models.chat import Chat
from app.db.models.user import User
from app.services.captcha_service import webapp_captcha_url
from app.services.gban_service import GbanService

logger = logging.getLogger(__name__)

router = Router()


@router.chat_join_request()
async def on_chat_join_request(
    event: ChatJoinRequest,
    session: AsyncSession,
    db_chat: Chat,
    user: User,
) -> None:
    """
    Guard-bot: заявка на вступление гейтится WebApp-капчой (Bot API 10.2, 10-сек бюджет).

    Query обязан быть отвечен всегда: `captcha_enabled=False` -> queue (решают админы
    вручную); гбан -> decline; trusted/moderator/has_passed_captcha -> approve; иначе --
    идемпотентная резервация сессии капчи (ON CONFLICT DO NOTHING по
    join_request_query_id) ДО показа Mini App -- повторный update с тем же query_id
    (ретрай Telegram) переиспользует уже созданный token вместо дубля. Сбой показа
    Mini App или публикации таймаут-задачи не должен оставить query без ответа --
    сессия переводится в EXPIRED и query уходит в queue.

    i18n здесь недоступен (нет i18n-middleware на update-типе chat_join_request) --
    только вызовы Telegram Bot API, без пользовательских текстов.
    """
    query_id = event.query_id
    if query_id is None:
        return

    async def _answer(result: str) -> None:
        try:
            await bot.answer_chat_join_request_query(chat_join_request_query_id=query_id, result=result)
        except TelegramBadRequest as e:
            logger.warning(f"answer_chat_join_request_query({result}) failed for {query_id}: {e}")

    if not db_chat.captcha_enabled:
        await _answer("queue")
        return

    if db_chat.gban_enabled and await GbanService.is_banned(user.id):
        await _answer("decline")
        try:
            banned = await safe_ban_member(bot, event.chat.id, user.id)
            if not banned:
                logger.warning(f"Cannot gban user {user.id} in {event.chat.id} (no restrict rights)")
        except Exception as e:
            logger.error(f"Failed to gban user {user.id} in {event.chat.id}: {e}")
        return

    if user.is_trusted or user.is_bot_moderator or user.has_passed_captcha:
        await _answer("approve")
        return

    token = secrets.token_urlsafe(32)
    stmt = (
        insert(ChatCaptchaSession)
        .values(
            chat_id=event.chat.id,
            user_id=user.id,
            kind=CaptchaSessionKind.JOIN_REQUEST,
            join_request_query_id=query_id,
            token=token,
            expires_at=datetime.now().astimezone() + timedelta(seconds=db_chat.captcha_timeout),
        )
        .on_conflict_do_nothing(index_elements=["join_request_query_id"])
        .returning(ChatCaptchaSession.id)
    )
    row = (await session.execute(stmt)).first()
    await session.commit()

    if row is None:  # дубликат update: строка уже есть -> переиспользовать её token
        existing = await session.scalar(
            select(ChatCaptchaSession).where(ChatCaptchaSession.join_request_query_id == query_id)
        )
        if existing is None:  # строка исчезла между конфликтом и SELECT -- отвечать нечем создать
            await _answer("queue")
            return
        token, session_id = existing.token, existing.id
        resend = True
    else:
        session_id, resend = row[0], False

    try:
        await bot.send_chat_join_request_web_app(
            chat_join_request_query_id=query_id, web_app_url=webapp_captcha_url(token), request_timeout=8
        )
    except (TelegramBadRequest, TelegramNetworkError) as e:
        logger.warning(f"send_chat_join_request_web_app failed for {query_id}: {e}")
        await claim_session(session, session_id, CaptchaSessionStatus.EXPIRED)
        await _answer("queue")
        return

    # resend (conflict-ветка) обязана переиздать таймаут тоже -- если оригинальный handler
    # умер после commit до publish, сессия иначе зависла бы PENDING навсегда. Дубликат
    # таймаут-сообщения безопасен -- воркер идемпотентен через claim(EXPIRED).
    delay_seconds = (
        max(1, int((existing.expires_at - datetime.now().astimezone()).total_seconds()))
        if resend
        else db_chat.captcha_timeout
    )
    try:
        await broker.publish(
            message={"chat_id": event.chat.id, "user_id": user.id, "session_id": session_id},
            exchange=delayed_exchange,
            routing_key="q.captcha.joinreq_timeout",
            headers={"x-delay": delay_seconds * 1000},
            persist=True,
        )
    except Exception as e:
        logger.error(f"Timeout publish failed for join request {query_id}: {e}")
        await claim_session(session, session_id, CaptchaSessionStatus.EXPIRED)
        await _answer("queue")
