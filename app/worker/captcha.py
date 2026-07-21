import asyncio
import logging
from datetime import datetime, timedelta
from enum import StrEnum

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from app.bot.instance import bot
from app.core.broker import broker, schedule_autodelete
from app.core.database import engine
from app.core.i18n import ROOT_LOCALE, translator_hub
from app.core.safe_telegram import safe_ban_member, safe_unban_member
from app.core.valkey import valkey
from app.db.models.captcha_session import CaptchaSessionStatus, ChatCaptchaSession, claim_session
from app.db.models.chat import Chat
from faststream.rabbit import RabbitExchange
from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class ExchangeTypeCustom(StrEnum):
    X_DELAYED_MESSAGE = "x-delayed-message"


delayed_exchange = RabbitExchange(
    name="delayed_exchange",
    type=ExchangeTypeCustom.X_DELAYED_MESSAGE,
    arguments={"x-delayed-type": "direct"},
)


@broker.subscriber("q.captcha.kick", exchange=delayed_exchange)
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


@broker.subscriber("q.captcha.joinreq_timeout", exchange=delayed_exchange)
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
