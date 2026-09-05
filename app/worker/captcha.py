import asyncio
import html
import logging
from datetime import datetime, timedelta
from enum import StrEnum

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from app.bot.instance import bot
from app.core.broker import broker, schedule_autodelete
from app.core.database import engine
from app.core.i18n import ROOT_LOCALE, translator_hub
from app.core.safe_telegram import safe_ban_member, safe_delete_message, safe_send_message, safe_unban_member
from app.core.valkey import valkey
from app.db.models.captcha_session import CaptchaSessionStatus, ChatCaptchaSession, claim_session
from app.db.models.chat import Chat
from app.db.models.user import User
from app.services.captcha_service import CaptchaService, build_captcha_keyboard, captcha_emoji_text
from faststream.rabbit import RabbitExchange, RabbitQueue
from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class ExchangeTypeCustom(StrEnum):
    X_DELAYED_MESSAGE = "x-delayed-message"


delayed_exchange = RabbitExchange(
    name="delayed_exchange",
    type=ExchangeTypeCustom.X_DELAYED_MESSAGE,
    arguments={"x-delayed-type": "direct"},
    durable=True,  # переживает рестарт RabbitMQ -- задачи капчи не теряются при деплое
)


@broker.subscriber(RabbitQueue("q.captcha.kick", durable=True), exchange=delayed_exchange)
async def kick_unverified_user(chat_id: int, user_id: int, session_id: int) -> None:
    """
    Задача для кика пользователя, не прошедшего капчу.
    """
    logger.info(f"Checking captcha status for user {user_id} in chat {chat_id}")

    async with async_session() as session:
        captcha_session = await session.get(ChatCaptchaSession, session_id)

        if not captcha_session:
            logger.warning(f"Captcha session {session_id} not found")
            return

        if captcha_session.expires_at > datetime.now().astimezone():
            logger.info(f"Captcha session {session_id} not yet expired")
            return

        claimed = await claim_session(session, captcha_session.id, CaptchaSessionStatus.EXPIRED)
        if not claimed:
            logger.info(f"Captcha session {session_id} already finalized, skip kick")
            return

        async def _do_kick() -> None:
            banned = await safe_ban_member(bot, chat_id, user_id, until_date=timedelta(minutes=1))
            if not banned:
                logger.debug(f"Skipped kicking user {user_id} in {chat_id} (no restrict rights cached)")
                return
            await safe_unban_member(bot, chat_id, user_id)

            lang_code = await valkey.get(f"lang:{chat_id}")
            i18n = translator_hub.get_translator_by_locale(lang_code or ROOT_LOCALE)
            kick_text = i18n.captcha.timeout.kick()

            # Гибридная доставка: у сессии могут жить оба сообщения сразу,
            # закрывать надо каждое.
            if captcha_session.ephemeral_message_id is not None:
                try:
                    await bot.edit_ephemeral_message_text(
                        chat_id=chat_id,
                        receiver_user_id=user_id,
                        ephemeral_message_id=captcha_session.ephemeral_message_id,
                        text=kick_text,
                    )
                except (TelegramBadRequest, TelegramForbiddenError) as e:
                    logger.warning(f"Failed to edit ephemeral message: {e}")

            if captcha_session.message_id is None:
                return

            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=captcha_session.message_id,
                    text=kick_text,
                )
            except TelegramBadRequest as e:
                logger.warning(f"Failed to edit message: {e}")

            try:
                db_chat = await session.get(Chat, chat_id)
                if db_chat:
                    await schedule_autodelete(
                        chat_id,
                        captcha_session.message_id,
                        db_chat.autodelete_settings,
                        "captcha_timeout",
                    )
            except Exception as e:
                logger.warning(f"Failed to schedule autodelete for captcha timeout: {e}")

        try:
            await _do_kick()
        except TelegramRetryAfter as e:
            logger.warning(f"Flood control kicking user {user_id} in {chat_id}, retry in {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            try:
                await _do_kick()
            except Exception as retry_err:
                logger.error(f"Failed to kick user {user_id} after retry: {retry_err}")
        except Exception as e:
            logger.error(f"Failed to kick user {user_id}: {e}")


def _mention_html(user_id: int, db_user: User | None) -> str:
    """HTML-упоминание вне контекста апдейта: у воркера нет aiogram-объекта User."""
    name = " ".join(filter(None, (db_user.first_name, db_user.last_name))) if db_user else ""
    return f'<a href="tg://user?id={user_id}">{html.escape(name or str(user_id))}</a>'


@broker.subscriber(RabbitQueue("q.captcha.fallback", durable=True), exchange=delayed_exchange)
async def send_public_captcha_fallback(chat_id: int, user_id: int, session_id: int) -> None:
    """
    Публичный дубль капчи: эфемерное сообщение Telegram доставляет без гарантий
    ("It is not guaranteed that the user will receive the message"), и молчание
    новичка чаще значит "не увидел", а не "не хочет".

    Дубль показывает ТУ ЖЕ раскладку из Valkey -- перегенерация превратила бы
    отставшее эфемерное сообщение в ловушку со списанием попытки. Не шлём, если
    сессия финализирована, истекла, уже публичная или человек жал кнопки.
    """
    async with async_session() as session:
        captcha_session = await session.get(ChatCaptchaSession, session_id)

        if not captcha_session:
            logger.warning(f"Captcha session {session_id} not found, skip public fallback")
            return

        if captcha_session.status != CaptchaSessionStatus.PENDING:
            logger.info(f"Captcha session {session_id} already finalized, skip public fallback")
            return

        if captcha_session.message_id is not None:
            logger.info(f"Captcha session {session_id} is already public, skip fallback")
            return

        if captcha_session.ephemeral_message_id is None:
            logger.info(f"Captcha session {session_id} has no ephemeral message, skip fallback")
            return

        if captcha_session.expires_at <= datetime.now().astimezone():
            logger.info(f"Captcha session {session_id} expired, skip public fallback")
            return

        chat = await session.get(Chat, chat_id)
        if chat is None:
            logger.warning(f"Chat {chat_id} not found, skip public captcha fallback")
            return

        lang_code = await valkey.get(f"lang:{chat_id}")
        i18n = translator_hub.get_translator_by_locale(lang_code or ROOT_LOCALE)
        mention = _mention_html(user_id, await session.get(User, user_id))

        if chat.captcha_type == "emoji":
            captcha_data = await CaptchaService.get_session(chat_id, user_id)
            if captcha_data is None or not captcha_data.buttons:
                logger.info(f"Captcha layout for session {session_id} is gone, skip public fallback")
                return
            if captcha_data.attempts_left < chat.captcha_max_attempts:
                logger.info(f"User {user_id} already answered captcha {session_id}, skip public fallback")
                return
            keyboard = build_captcha_keyboard(user_id, captcha_data.buttons)
            msg_text = captcha_emoji_text(i18n, mention, captcha_data.target_emoji, captcha_data.target_style)
        else:
            bot_info = await bot.get_me()
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=i18n.btn.verify(),
                            url=f"https://t.me/{bot_info.username}?start=captcha_{captcha_session.id}",
                        )
                    ]
                ]
            )
            msg_text = i18n.captcha.verify(user=mention)

        try:
            sent = await safe_send_message(bot, chat_id, text=msg_text, reply_markup=keyboard, parse_mode="HTML")
        except TelegramRetryAfter as e:
            logger.warning(f"Flood control on public captcha fallback in {chat_id}, retry in {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            try:
                sent = await safe_send_message(bot, chat_id, text=msg_text, reply_markup=keyboard, parse_mode="HTML")
            except Exception as retry_err:
                logger.error(f"Public captcha fallback failed after retry in {chat_id}: {retry_err}")
                return
        except Exception as e:
            logger.error(f"Public captcha fallback failed in {chat_id}: {e}")
            return

        if sent is None:
            logger.debug(f"Skipped public captcha fallback in {chat_id} (no send rights cached)")
            return

        # Сессию могли финализировать, пока летел send -- тогда дубль осиротеет в чате
        await session.refresh(captcha_session)
        if captcha_session.status != CaptchaSessionStatus.PENDING:
            logger.info(f"Captcha session {session_id} finalized mid-send, removing public fallback")
            try:
                await safe_delete_message(bot, chat_id, sent.message_id)
            except Exception as e:
                logger.warning(f"Failed to remove orphaned public captcha in {chat_id}: {e}")
            return

        captcha_session.message_id = sent.message_id
        await session.commit()


@broker.subscriber(RabbitQueue("q.captcha.joinreq_timeout", durable=True), exchange=delayed_exchange)
async def expire_join_request(chat_id: int, user_id: int, session_id: int) -> None:
    """
    Таймаут заявки на вступление, не решённой WebApp-капчой.

    claim(EXPIRED) -> decline query + бан на срок `chat.captcha_ban_duration`.
    Проигранный claim (юзер успел решить капчу через /solve первым) -- выход
    без side effects. Исключение Telegram при decline/бане -- залогировать и
    выйти (заявка остаётся висеть админам -- осознанная деградация).
    """
    logger.info(f"Checking join-request captcha status for user {user_id} in chat {chat_id}")

    async with async_session() as session:
        captcha_session = await session.get(ChatCaptchaSession, session_id)

        if not captcha_session:
            logger.warning(f"Join-request captcha session {session_id} not found")
            return

        claimed = await claim_session(session, captcha_session.id, CaptchaSessionStatus.EXPIRED)
        if not claimed:
            logger.info(f"Join-request session {session_id} already finalized, skip decline")
            return

        chat = await session.get(Chat, chat_id)
        if chat is None:  # FK гарантирует существование строки в норме -- почти мёртвая ветка
            logger.warning(f"Chat {chat_id} not found, skip decline/ban for join request user {user_id}")
            return

        try:
            await bot.answer_chat_join_request_query(
                chat_join_request_query_id=captcha_session.join_request_query_id,
                result="decline",
            )
            await safe_ban_member(bot, chat_id, user_id, until_date=timedelta(seconds=chat.captcha_ban_duration))
        except Exception as e:
            logger.error(f"Failed to decline/ban join request user {user_id} in {chat_id}: {e}")
