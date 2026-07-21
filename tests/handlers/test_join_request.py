"""Тесты guard-bot handler'а (chat_join_request) и таймаут-воркера заявок на вступление.

Флоу — task-9-brief.md: идемпотентная резервация сессии капчи ДО показа Mini App
(on_conflict_do_nothing по join_request_query_id), query обязан быть отвечен всегда
(queue при captcha off/сбоях), claim(EXPIRED) в таймаут-воркере.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import func, select

from app.bot.handlers.join_request import on_chat_join_request
from app.db.models.captcha_session import CaptchaSessionKind, CaptchaSessionStatus, ChatCaptchaSession
from app.worker.captcha import expire_join_request
from tests.factories import create_chat, create_user

pytestmark = pytest.mark.asyncio

CHAT_ID = -100777777
USER_ID = 555555


# ── Helpers ───────────────────────────────────────────────────────────────────


def _bad_request(text: str = "Bad Request: QUERY_ID_INVALID") -> TelegramBadRequest:
    return TelegramBadRequest(method=MagicMock(), message=text)


def _make_event(chat_id: int = CHAT_ID, user_id: int = USER_ID, query_id: str | None = "query-1") -> MagicMock:
    """Duck-typed ChatJoinRequest: только поля, которые реально читает handler."""
    chat = MagicMock()
    chat.id = chat_id

    from_user = MagicMock()
    from_user.id = user_id

    event = MagicMock()
    event.chat = chat
    event.from_user = from_user
    event.query_id = query_id
    return event


def _make_bot() -> MagicMock:
    mock_bot = MagicMock()
    mock_bot.answer_chat_join_request_query = AsyncMock()
    mock_bot.send_chat_join_request_web_app = AsyncMock()
    mock_bot.ban_chat_member = AsyncMock()
    return mock_bot


def _make_broker() -> MagicMock:
    mock_broker = MagicMock()
    mock_broker.publish = AsyncMock()
    return mock_broker


async def _fetch_by_query_id(db_session, query_id: str) -> ChatCaptchaSession | None:
    stmt = select(ChatCaptchaSession).where(ChatCaptchaSession.join_request_query_id == query_id)
    result = await db_session.execute(stmt)
    return result.scalars().first()


async def _count_by_query_id(db_session, query_id: str) -> int:
    stmt = (
        select(func.count()).select_from(ChatCaptchaSession).where(ChatCaptchaSession.join_request_query_id == query_id)
    )
    return await db_session.scalar(stmt) or 0


async def _seed_join_session(db_session, **overrides) -> ChatCaptchaSession:
    defaults = dict(
        chat_id=CHAT_ID,
        user_id=USER_ID,
        kind=CaptchaSessionKind.JOIN_REQUEST,
        join_request_query_id="q-timeout",
        status=CaptchaSessionStatus.PENDING,
        expires_at=datetime.now().astimezone() - timedelta(seconds=1),
    )
    defaults.update(overrides)
    session_obj = ChatCaptchaSession(**defaults)
    db_session.add(session_obj)
    await db_session.commit()
    await db_session.refresh(session_obj)
    return session_obj


# ── query_id отсутствует ───────────────────────────────────────────────────────


async def test_no_query_id_returns_without_answer(db_session, monkeypatch):
    """Нет query_id -- отвечать нечем, handler молча выходит без вызовов Telegram."""
    chat = await create_chat(db_session, id=CHAT_ID, captcha_enabled=True)
    user = await create_user(db_session, id=USER_ID)
    await db_session.commit()

    mock_bot = _make_bot()
    monkeypatch.setattr("app.bot.handlers.join_request.bot", mock_bot)

    event = _make_event(query_id=None)
    await on_chat_join_request(event, db_session, chat, user)

    mock_bot.answer_chat_join_request_query.assert_not_awaited()


# ── captcha_enabled=False -> queue ────────────────────────────────────────────


async def test_captcha_disabled_answers_queue(db_session, monkeypatch):
    """Капча выключена в чате -- query обязан быть отвечен result='queue' (решают админы)."""
    chat = await create_chat(db_session, id=CHAT_ID, captcha_enabled=False)
    user = await create_user(db_session, id=USER_ID)
    await db_session.commit()

    mock_bot = _make_bot()
    monkeypatch.setattr("app.bot.handlers.join_request.bot", mock_bot)

    event = _make_event(query_id="q-disabled")
    await on_chat_join_request(event, db_session, chat, user)

    mock_bot.answer_chat_join_request_query.assert_awaited_once_with(
        chat_join_request_query_id="q-disabled", result="queue"
    )
    mock_bot.send_chat_join_request_web_app.assert_not_awaited()
    assert await _fetch_by_query_id(db_session, "q-disabled") is None


# ── гбан -> decline + бан ──────────────────────────────────────────────────────


async def test_gban_declines_and_bans(db_session, monkeypatch):
    """Юзер в гбан-листе (при gban_enabled) -- decline + safe_ban_member, капча не создаётся."""
    chat = await create_chat(db_session, id=CHAT_ID, captcha_enabled=True, gban_enabled=True)
    user = await create_user(db_session, id=USER_ID)
    await db_session.commit()

    mock_bot = _make_bot()
    monkeypatch.setattr("app.bot.handlers.join_request.bot", mock_bot)
    monkeypatch.setattr("app.bot.handlers.join_request.GbanService.is_banned", AsyncMock(return_value=True))

    event = _make_event(query_id="q-gban")
    await on_chat_join_request(event, db_session, chat, user)

    mock_bot.answer_chat_join_request_query.assert_awaited_once_with(
        chat_join_request_query_id="q-gban", result="decline"
    )
    mock_bot.ban_chat_member.assert_awaited_once()
    assert await _fetch_by_query_id(db_session, "q-gban") is None


async def test_gban_disabled_skips_ban_check(db_session, monkeypatch):
    """gban_enabled=False -- гбан-лист не проверяется, юзер идёт в обычный флоу капчи."""
    chat = await create_chat(db_session, id=CHAT_ID, captcha_enabled=True, gban_enabled=False)
    user = await create_user(db_session, id=USER_ID)
    await db_session.commit()

    mock_bot = _make_bot()
    mock_broker = _make_broker()
    monkeypatch.setattr("app.bot.handlers.join_request.bot", mock_bot)
    monkeypatch.setattr("app.bot.handlers.join_request.broker", mock_broker)
    is_banned_mock = AsyncMock(return_value=True)
    monkeypatch.setattr("app.bot.handlers.join_request.GbanService.is_banned", is_banned_mock)

    event = _make_event(query_id="q-gban-off")
    await on_chat_join_request(event, db_session, chat, user)

    is_banned_mock.assert_not_awaited()
    mock_bot.send_chat_join_request_web_app.assert_awaited_once()


# ── trusted/moderator/has_passed_captcha -> approve ───────────────────────────


@pytest.mark.parametrize("field", ["is_trusted", "is_bot_moderator", "has_passed_captcha"])
async def test_pretrusted_user_approved(db_session, monkeypatch, field):
    """trusted/moderator/has_passed_captcha -- сразу approve, без показа капчи."""
    chat = await create_chat(db_session, id=CHAT_ID, captcha_enabled=True)
    user = await create_user(db_session, id=USER_ID, **{field: True})
    await db_session.commit()

    mock_bot = _make_bot()
    monkeypatch.setattr("app.bot.handlers.join_request.bot", mock_bot)

    event = _make_event(query_id="q-trusted")
    await on_chat_join_request(event, db_session, chat, user)

    mock_bot.answer_chat_join_request_query.assert_awaited_once_with(
        chat_join_request_query_id="q-trusted", result="approve"
    )
    mock_bot.send_chat_join_request_web_app.assert_not_awaited()
    assert await _fetch_by_query_id(db_session, "q-trusted") is None


# ── новая заявка -> резервация сессии + Mini App + таймаут-задача ─────────────


async def test_new_request_creates_session_sends_webapp_and_schedules_timeout(db_session, monkeypatch):
    """Новая заявка: сессия создаётся ДО показа Mini App, таймаут-задача публикуется."""
    chat = await create_chat(db_session, id=CHAT_ID, captcha_enabled=True, captcha_timeout=120)
    user = await create_user(db_session, id=USER_ID)
    await db_session.commit()

    mock_bot = _make_bot()
    mock_broker = _make_broker()
    monkeypatch.setattr("app.bot.handlers.join_request.bot", mock_bot)
    monkeypatch.setattr("app.bot.handlers.join_request.broker", mock_broker)

    event = _make_event(query_id="q-new")
    await on_chat_join_request(event, db_session, chat, user)

    mock_bot.answer_chat_join_request_query.assert_not_awaited()

    session_obj = await _fetch_by_query_id(db_session, "q-new")
    assert session_obj is not None
    assert session_obj.kind == CaptchaSessionKind.JOIN_REQUEST
    assert session_obj.status == CaptchaSessionStatus.PENDING
    assert session_obj.chat_id == CHAT_ID
    assert session_obj.user_id == USER_ID

    mock_bot.send_chat_join_request_web_app.assert_awaited_once()
    _, kwargs = mock_bot.send_chat_join_request_web_app.call_args
    assert kwargs["chat_join_request_query_id"] == "q-new"
    assert session_obj.token in kwargs["web_app_url"]

    mock_broker.publish.assert_awaited_once()
    _, publish_kwargs = mock_broker.publish.call_args
    assert publish_kwargs["message"] == {
        "chat_id": CHAT_ID,
        "user_id": USER_ID,
        "session_id": session_obj.id,
    }
    assert publish_kwargs["routing_key"] == "q.captcha.joinreq_timeout"
    assert publish_kwargs["headers"] == {"x-delay": 120 * 1000}


async def test_duplicate_update_reuses_token_no_second_insert(db_session, monkeypatch):
    """Повторный update с тем же query_id (ретрай Telegram) переиспользует token без дубля строки."""
    chat = await create_chat(db_session, id=CHAT_ID, captcha_enabled=True)
    user = await create_user(db_session, id=USER_ID)
    await db_session.commit()

    existing = ChatCaptchaSession(
        chat_id=CHAT_ID,
        user_id=USER_ID,
        kind=CaptchaSessionKind.JOIN_REQUEST,
        join_request_query_id="q-dup",
        token="existing-token-123",
        expires_at=datetime.now().astimezone() + timedelta(minutes=5),
    )
    db_session.add(existing)
    await db_session.commit()
    await db_session.refresh(existing)

    mock_bot = _make_bot()
    mock_broker = _make_broker()
    monkeypatch.setattr("app.bot.handlers.join_request.bot", mock_bot)
    monkeypatch.setattr("app.bot.handlers.join_request.broker", mock_broker)

    event = _make_event(query_id="q-dup")
    await on_chat_join_request(event, db_session, chat, user)

    assert await _count_by_query_id(db_session, "q-dup") == 1
    mock_bot.send_chat_join_request_web_app.assert_awaited_once()
    _, kwargs = mock_bot.send_chat_join_request_web_app.call_args
    assert "existing-token-123" in kwargs["web_app_url"]
    mock_broker.publish.assert_not_awaited()  # resend -> таймаут-задача не переиздаётся повторно


async def test_send_webapp_failure_expires_session_and_queues(db_session, monkeypatch):
    """send_chat_join_request_web_app упал TelegramBadRequest -- сессия EXPIRED, query queue."""
    chat = await create_chat(db_session, id=CHAT_ID, captcha_enabled=True)
    user = await create_user(db_session, id=USER_ID)
    await db_session.commit()

    mock_bot = _make_bot()
    mock_bot.send_chat_join_request_web_app = AsyncMock(side_effect=_bad_request())
    mock_broker = _make_broker()
    monkeypatch.setattr("app.bot.handlers.join_request.bot", mock_bot)
    monkeypatch.setattr("app.bot.handlers.join_request.broker", mock_broker)

    event = _make_event(query_id="q-webapp-fail")
    await on_chat_join_request(event, db_session, chat, user)

    session_obj = await _fetch_by_query_id(db_session, "q-webapp-fail")
    assert session_obj.status == CaptchaSessionStatus.EXPIRED
    mock_bot.answer_chat_join_request_query.assert_awaited_once_with(
        chat_join_request_query_id="q-webapp-fail", result="queue"
    )
    mock_broker.publish.assert_not_awaited()


async def test_publish_failure_expires_session_and_queues(db_session, monkeypatch):
    """Таймаут-задача не опубликовалась -- сессия EXPIRED, query queue (без вечного PENDING)."""
    chat = await create_chat(db_session, id=CHAT_ID, captcha_enabled=True)
    user = await create_user(db_session, id=USER_ID)
    await db_session.commit()

    mock_bot = _make_bot()
    mock_broker = MagicMock()
    mock_broker.publish = AsyncMock(side_effect=RuntimeError("broker down"))
    monkeypatch.setattr("app.bot.handlers.join_request.bot", mock_bot)
    monkeypatch.setattr("app.bot.handlers.join_request.broker", mock_broker)

    event = _make_event(query_id="q-publish-fail")
    await on_chat_join_request(event, db_session, chat, user)

    session_obj = await _fetch_by_query_id(db_session, "q-publish-fail")
    assert session_obj.status == CaptchaSessionStatus.EXPIRED
    mock_bot.answer_chat_join_request_query.assert_awaited_once_with(
        chat_join_request_query_id="q-publish-fail", result="queue"
    )


# ── worker/captcha.py: expire_join_request (таймаут) ──────────────────────────


async def test_timeout_declines_and_bans(db_session, monkeypatch):
    """Таймаут заявки: claim(EXPIRED) -> decline + бан на chat.captcha_ban_duration."""
    chat = await create_chat(db_session, id=CHAT_ID, captcha_ban_duration=600)
    await create_user(db_session, id=USER_ID)
    session_obj = await _seed_join_session(db_session)

    mock_bot = _make_bot()
    monkeypatch.setattr("app.worker.captcha.bot", mock_bot)

    await expire_join_request(CHAT_ID, USER_ID, session_obj.id)

    mock_bot.answer_chat_join_request_query.assert_awaited_once_with(
        chat_join_request_query_id="q-timeout", result="decline"
    )
    mock_bot.ban_chat_member.assert_awaited_once()
    _, kwargs = mock_bot.ban_chat_member.call_args
    assert kwargs["until_date"] == timedelta(seconds=chat.captcha_ban_duration)

    await db_session.refresh(session_obj)
    assert session_obj.status == CaptchaSessionStatus.EXPIRED


async def test_timeout_claim_lost_skips_side_effects(db_session, monkeypatch):
    """Сессия уже PASSED (юзер успел решить капчу первым) -- claim проигран, decline/бан не зовутся."""
    await create_chat(db_session, id=CHAT_ID)
    await create_user(db_session, id=USER_ID)
    session_obj = await _seed_join_session(db_session, status=CaptchaSessionStatus.PASSED)

    mock_bot = _make_bot()
    monkeypatch.setattr("app.worker.captcha.bot", mock_bot)

    await expire_join_request(CHAT_ID, USER_ID, session_obj.id)

    mock_bot.answer_chat_join_request_query.assert_not_awaited()
    mock_bot.ban_chat_member.assert_not_awaited()


async def test_timeout_session_not_found_noop(db_session, monkeypatch):
    """Сессия не найдена (например, удалена) -- воркер тихо выходит без ошибок."""
    mock_bot = _make_bot()
    monkeypatch.setattr("app.worker.captcha.bot", mock_bot)

    await expire_join_request(CHAT_ID, USER_ID, 999_999_999)

    mock_bot.answer_chat_join_request_query.assert_not_awaited()
