import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter
from aiogram.utils.web_app import WebAppInitData, safe_parse_webapp_init_data
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, validate_init_data
from app.bot.instance import bot
from app.core.config import settings
from app.core.i18n import ROOT_LOCALE, translator_hub
from app.core.safe_telegram import full_permissions
from app.core.valkey import valkey
from app.db.models.captcha_session import CaptchaSessionKind, CaptchaSessionStatus, ChatCaptchaSession, claim_session
from app.db.models.chat import Chat
from app.db.models.user import User
from app.services.captcha_service import webapp_captcha_url
from app.services.user_service import get_or_create_user

router = APIRouter()
logger = logging.getLogger(__name__)


class SolveCaptchaRequest(BaseModel):
    """Тело запроса `/solve` — опциональный token конкретной сессии капчи."""

    token: str | None = None


def _get_webapp_data(auth_info: dict) -> WebAppInitData:
    """
    Общая проверка auth_info для webapp-эндпоинтов капчи.

    Бросает 400, если авторизация не webapp-типа или в initData нет пользователя;
    401, если initData не парсится (невалидная подпись).
    """
    if auth_info["type"] != "webapp":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only WebApp authentication is supported",
        )

    try:
        web_app_data = safe_parse_webapp_init_data(settings.BOT_TOKEN, auth_info["data"])
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid initData",
        ) from e

    if not web_app_data.user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User data missing",
        )

    return web_app_data


async def _resolve_captcha_session(session: AsyncSession, user_id: int, token: str | None) -> ChatCaptchaSession | None:
    """
    Находит сессию капчи для `/check`/`/solve`.

    С token — SELECT по token+user_id БЕЗ фильтра статуса, затем маппинг статуса на HTTP:
    PENDING и не истекла -> возвращает сессию; PASSED/APPROVED/DECLINED -> 409 (уже
    финализирована); EXPIRED или истёкшая PENDING -> 404 "Session expired"; не найдена -> 404.

    Без token — легаси-путь (на один релиз, для ещё не обновившегося фронтенда): последняя
    PENDING сессия kind=chat для юзера, ORDER BY created_at DESC. Отсутствие сессии — не
    ошибка (возвращается None), решение о статус-коде остаётся за вызывающей стороной.
    """
    now = datetime.now().astimezone()

    if token is not None:
        query = select(ChatCaptchaSession).where(
            ChatCaptchaSession.token == token,
            ChatCaptchaSession.user_id == user_id,
        )
        result = await session.execute(query)
        captcha_session = result.scalars().first()

        if captcha_session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Captcha session not found")

        if captcha_session.status == CaptchaSessionStatus.EXPIRED or (
            captcha_session.status == CaptchaSessionStatus.PENDING and captcha_session.expires_at <= now
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session expired")

        if captcha_session.status != CaptchaSessionStatus.PENDING:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session already finalized")

        return captcha_session

    query = (
        select(ChatCaptchaSession)
        .where(
            ChatCaptchaSession.kind == CaptchaSessionKind.CHAT,
            ChatCaptchaSession.user_id == user_id,
            ChatCaptchaSession.status == CaptchaSessionStatus.PENDING,
            ChatCaptchaSession.expires_at > now,
        )
        .order_by(ChatCaptchaSession.created_at.desc())
    )
    result = await session.execute(query)
    return result.scalars().first()


async def _answer_join_query_with_retry(query_id: str, result: str) -> None:
    """
    Отвечает на join-request query с ретраем транзиентных ошибок Telegram.

    `TelegramRetryAfter` — ждём `retry_after` секунд и повторяем один раз;
    `TelegramNetworkError` — повторяем один раз без задержки. `TelegramBadRequest`
    (query протух/уже отвечен) не ретраится — пробрасывается сразу, вызывающая
    сторона переводит сессию в EXPIRED. Если повторная попытка тоже падает
    (любым исключением) — пробрасывается дальше.
    """
    try:
        await bot.answer_chat_join_request_query(chat_join_request_query_id=query_id, result=result)
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        await bot.answer_chat_join_request_query(chat_join_request_query_id=query_id, result=result)
    except TelegramNetworkError:
        await bot.answer_chat_join_request_query(chat_join_request_query_id=query_id, result=result)


@router.get("/check")
async def check_captcha_status(
    token: str | None = None,
    auth_info: dict = Depends(validate_init_data),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Проверяет статус капчи для пользователя (по token, если передан, иначе легаси-путь).
    """
    web_app_data = _get_webapp_data(auth_info)
    user_id = web_app_data.user.id

    captcha_session = await _resolve_captcha_session(session, user_id, token)

    if captcha_session:
        return {
            "ok": True,
            "status": "pending",
            "session_id": captcha_session.id,
            "chat_id": captcha_session.chat_id,
            "kind": captcha_session.kind,
        }

    return {"ok": True, "status": "no_session"}


@router.post("/solve")
async def solve_captcha(
    body: SolveCaptchaRequest,
    auth_info: dict = Depends(validate_init_data),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Подтверждает прохождение капчи. Финализация (kind=chat) атомарна через `claim_session` —
    проигранная гонка (сессию уже финализировал другой запрос) возвращает 409.
    """
    web_app_data = _get_webapp_data(auth_info)
    user_id = web_app_data.user.id

    captcha_session = await _resolve_captcha_session(session, user_id, body.token)
    if not captcha_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Active captcha session not found",
        )

    if captcha_session.kind == CaptchaSessionKind.JOIN_REQUEST:
        claimed = await claim_session(session, captcha_session.id, CaptchaSessionStatus.PASSED)
        if not claimed:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session already finalized")
        # claim_session бьёт bulk UPDATE мимо identity map (synchronize_session=False) —
        # refresh нужен, иначе последующий set обратно в PENDING SQLAlchemy сочтёт net-zero
        # относительно закэшированного baseline (ещё PENDING) и молча пропустит UPDATE.
        await session.refresh(captcha_session)

        try:
            await _answer_join_query_with_retry(captcha_session.join_request_query_id, "approve")
        except TelegramBadRequest:
            captcha_session.status = CaptchaSessionStatus.EXPIRED
            await session.commit()
            return {"ok": False, "status": "expired", "kind": "join_request"}
        except (TelegramNetworkError, TelegramRetryAfter) as e:
            captcha_session.status = CaptchaSessionStatus.PENDING  # компенсация: юзер нажмёт Verify ещё раз
            await session.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Temporary failure, try again"
            ) from e

        captcha_session.status = CaptchaSessionStatus.APPROVED
        joined_user = await session.get(User, user_id)
        if joined_user:
            joined_user.has_passed_captcha = True
        await session.commit()
        return {"ok": True, "kind": captcha_session.kind}

    claimed = await claim_session(session, captcha_session.id, CaptchaSessionStatus.PASSED)
    if not claimed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session already finalized")

    user = await session.get(User, user_id)
    if user:
        user.has_passed_captcha = True
        await session.commit()

    try:
        await bot.restrict_chat_member(
            chat_id=captcha_session.chat_id,
            user_id=user_id,
            permissions=full_permissions(),
        )

        lang_code = await valkey.get(f"lang:{captcha_session.chat_id}")
        i18n = translator_hub.get_translator_by_locale(lang_code or ROOT_LOCALE)

        chat = await session.get(Chat, captcha_session.chat_id)
        welcome_shown = bool(chat and chat.welcome_enabled)

        if captcha_session.ephemeral_message_id is not None:
            if welcome_shown:
                await bot.edit_ephemeral_message_reply_markup(
                    chat_id=captcha_session.chat_id,
                    receiver_user_id=user_id,
                    ephemeral_message_id=captcha_session.ephemeral_message_id,
                    reply_markup=None,
                )
            else:
                await bot.edit_ephemeral_message_text(
                    chat_id=captcha_session.chat_id,
                    receiver_user_id=user_id,
                    ephemeral_message_id=captcha_session.ephemeral_message_id,
                    text=i18n.captcha.success(),
                )
        elif welcome_shown:
            await bot.edit_message_reply_markup(
                chat_id=captcha_session.chat_id,
                message_id=captcha_session.message_id,
                reply_markup=None,
            )
        else:
            await bot.edit_message_text(
                chat_id=captcha_session.chat_id,
                message_id=captcha_session.message_id,
                text=i18n.captcha.success(),
            )
    except Exception as e:
        logger.error(f"Failed to unmute user or edit message: {e}")

    return {"ok": True, "kind": captcha_session.kind}


@router.post("/debug")
async def create_debug_captcha(
    auth_info: dict = Depends(validate_init_data),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Создает тестовую сессию капчи для отладки (только для админов).
    """
    web_app_data = _get_webapp_data(auth_info)
    user_id = web_app_data.user.id

    user = await session.get(User, user_id)
    if not user:
        user = await get_or_create_user(
            session=session,
            user_id=user_id,
            username=web_app_data.user.username,
            first_name=web_app_data.user.first_name,
            last_name=web_app_data.user.last_name,
            language_code=web_app_data.user.language_code,
            is_premium=web_app_data.user.is_premium,
        )

    if user_id not in settings.BOT_ADMINS and not user.is_bot_moderator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: admin only",
        )

    expires_at = datetime.now().astimezone() + timedelta(minutes=10)  # Дольше для отладки

    captcha_session = ChatCaptchaSession(
        chat_id=user_id,
        user_id=user_id,
        expires_at=expires_at,
    )
    session.add(captcha_session)
    await session.commit()
    await session.refresh(captcha_session)

    return {
        "ok": True,
        "session_id": captcha_session.id,
        "expires_at": expires_at.isoformat(),
        "url": webapp_captcha_url(captcha_session.token),
    }
