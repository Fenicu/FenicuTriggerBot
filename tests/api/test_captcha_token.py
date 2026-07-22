"""Тесты token-привязки webapp-капчи: /api/v1/captcha/check и /solve.

Семантика (см. .superpowers/sdd/task-8-brief.md):
- С token: SELECT по token+user_id БЕЗ фильтра статуса, затем маппинг —
  PENDING и не истекла -> ok; PASSED/APPROVED/DECLINED -> 409; EXPIRED
  или истёкшая PENDING -> 404 "Session expired"; не найдена -> 404.
- Без token: легаси-путь (на один релиз) — последняя PENDING kind=chat
  сессия юзера, ORDER BY created_at DESC.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints import captcha as captcha_endpoint
from app.db.models.captcha_session import CaptchaSessionKind, CaptchaSessionStatus
from tests.factories import create_captcha_session, create_chat, create_user

pytestmark = pytest.mark.asyncio


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def captcha_client(db_session: AsyncSession):
    """
    Фабрика httpx-клиентов поверх FastAPI app для конкретного telegram user_id.

    `validate_init_data` задепенднут на webapp-заглушку (без реальной подписи initData),
    `safe_parse_webapp_init_data` застаблен объектом с `.user.id == user_id` — как просил
    координатор, чтобы не тащить в тест реальный HMAC Telegram WebApp.
    """
    from fastapi import FastAPI

    from app.api.deps import validate_init_data
    from app.api.v1.router import api_router
    from app.core.database import get_db

    @asynccontextmanager
    async def _make(user_id: int):
        test_app = FastAPI()
        test_app.include_router(api_router, prefix="/api/v1")

        async def _override_db():
            yield db_session

        async def _override_auth():
            return {"type": "webapp", "data": "stub-init-data"}

        test_app.dependency_overrides[get_db] = _override_db
        test_app.dependency_overrides[validate_init_data] = _override_auth

        stub_user = SimpleNamespace(
            id=user_id,
            username="tester",
            first_name="Test",
            last_name=None,
            language_code="en",
            is_premium=False,
        )
        stub_init_data = SimpleNamespace(user=stub_user)

        with patch(
            "app.api.v1.endpoints.captcha.safe_parse_webapp_init_data",
            return_value=stub_init_data,
        ):
            transport = ASGITransport(app=test_app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                yield client

    return _make


# ── /check — с token ───────────────────────────────────────────────────────────


async def test_check_with_token_pending_returns_session_and_kind(db_session, captcha_client):
    """Валидный token PENDING-сессии -> ok=True, статус pending, kind в ответе."""
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    session_obj = await create_captcha_session(db_session, chat.id, user.id)
    await db_session.commit()

    async with captcha_client(user.id) as client:
        resp = await client.get("/api/v1/captcha/check", params={"token": session_obj.token})

    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "ok": True,
        "status": "pending",
        "session_id": session_obj.id,
        "chat_id": chat.id,
        "kind": "chat",
    }


async def test_check_with_unknown_token_404(db_session, captcha_client):
    """Токен, которого нет ни у одной сессии этого юзера -> 404."""
    user = await create_user(db_session)
    await db_session.commit()

    async with captcha_client(user.id) as client:
        resp = await client.get("/api/v1/captcha/check", params={"token": "does-not-exist"})

    assert resp.status_code == 404


async def test_check_token_belongs_to_other_user_404(db_session, captcha_client):
    """Токен существует, но принадлежит сессии ДРУГОГО юзера -> не находится (404)."""
    chat = await create_chat(db_session)
    owner = await create_user(db_session)
    intruder = await create_user(db_session)
    session_obj = await create_captcha_session(db_session, chat.id, owner.id)
    await db_session.commit()

    async with captcha_client(intruder.id) as client:
        resp = await client.get("/api/v1/captcha/check", params={"token": session_obj.token})

    assert resp.status_code == 404


@pytest.mark.parametrize(
    "status",
    [CaptchaSessionStatus.PASSED, CaptchaSessionStatus.APPROVED, CaptchaSessionStatus.DECLINED],
)
async def test_check_with_token_finalized_status_409(db_session, captcha_client, status):
    """Сессия по token уже финализирована (PASSED/APPROVED/DECLINED) -> 409."""
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    session_obj = await create_captcha_session(db_session, chat.id, user.id, status=status)
    await db_session.commit()

    async with captcha_client(user.id) as client:
        resp = await client.get("/api/v1/captcha/check", params={"token": session_obj.token})

    assert resp.status_code == 409
    assert resp.json()["detail"] == "Session already finalized"


async def test_check_with_token_expired_status_404(db_session, captcha_client):
    """status=EXPIRED -> 404 'Session expired'."""
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    session_obj = await create_captcha_session(db_session, chat.id, user.id, status=CaptchaSessionStatus.EXPIRED)
    await db_session.commit()

    async with captcha_client(user.id) as client:
        resp = await client.get("/api/v1/captcha/check", params={"token": session_obj.token})

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Session expired"


async def test_check_with_token_pending_but_time_expired_404(db_session, captcha_client):
    """status=PENDING, но expires_at уже в прошлом (воркер-реапер ещё не пробежал) -> 404 'Session expired'."""
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    session_obj = await create_captcha_session(
        db_session,
        chat.id,
        user.id,
        expires_at=datetime.now().astimezone() - timedelta(minutes=1),
    )
    await db_session.commit()

    async with captcha_client(user.id) as client:
        resp = await client.get("/api/v1/captcha/check", params={"token": session_obj.token})

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Session expired"


# ── /check — без token (легаси) ─────────────────────────────────────────────────


async def test_check_no_token_no_session_returns_no_session(db_session, captcha_client):
    """Без token и без легаси-сессии -> {"ok": True, "status": "no_session"} (НЕ ошибка)."""
    user = await create_user(db_session)
    await db_session.commit()

    async with captcha_client(user.id) as client:
        resp = await client.get("/api/v1/captcha/check")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "status": "no_session"}


# ── /solve — с token ───────────────────────────────────────────────────────────


async def test_solve_with_token_success_finalizes_session(db_session, captcha_client):
    """Валидный token PENDING-сессии -> claim_session атомарно PASSED, ok=True, kind в ответе."""
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    session_obj = await create_captcha_session(db_session, chat.id, user.id)
    await db_session.commit()

    async with captcha_client(user.id) as client:
        resp = await client.post("/api/v1/captcha/solve", json={"token": session_obj.token})

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "kind": "chat"}

    await db_session.refresh(session_obj)
    assert session_obj.status == CaptchaSessionStatus.PASSED

    await db_session.refresh(user)
    assert user.has_passed_captcha is True


async def test_solve_finalized_session_409(db_session, captcha_client):
    """token уже PASSED-сессии -> 409 (новая семантика: маппинг статуса, не только claim-race)."""
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    session_obj = await create_captcha_session(db_session, chat.id, user.id, status=CaptchaSessionStatus.PASSED)
    await db_session.commit()

    async with captcha_client(user.id) as client:
        resp = await client.post("/api/v1/captcha/solve", json={"token": session_obj.token})

    assert resp.status_code == 409
    assert resp.json()["detail"] == "Session already finalized"


async def test_solve_expired_token_404(db_session, captcha_client):
    """token EXPIRED-сессии -> 404 'Session expired'."""
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    session_obj = await create_captcha_session(db_session, chat.id, user.id, status=CaptchaSessionStatus.EXPIRED)
    await db_session.commit()

    async with captcha_client(user.id) as client:
        resp = await client.post("/api/v1/captcha/solve", json={"token": session_obj.token})

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Session expired"


async def test_solve_unknown_token_404(db_session, captcha_client):
    """Несуществующий token -> 404 (нет сессии — нечего решать)."""
    user = await create_user(db_session)
    await db_session.commit()

    async with captcha_client(user.id) as client:
        resp = await client.post("/api/v1/captcha/solve", json={"token": "nope"})

    assert resp.status_code == 404


async def test_solve_lost_claim_race_returns_409(db_session, captcha_client):
    """
    Сессия проходит маппинг (PENDING, не истекла), но claim_session проигрывает гонку
    (конкурентный /solve уже забрал PENDING->PASSED первым) -> 409, без side effects.
    """
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    session_obj = await create_captcha_session(db_session, chat.id, user.id)
    await db_session.commit()

    with patch("app.api.v1.endpoints.captcha.claim_session", return_value=False) as mock_claim:
        async with captcha_client(user.id) as client:
            resp = await client.post("/api/v1/captcha/solve", json={"token": session_obj.token})

    assert resp.status_code == 409
    assert resp.json()["detail"] == "Session already finalized"
    mock_claim.assert_awaited_once()


# ── /solve — без token (легаси, один релиз) ─────────────────────────────────────


async def test_solve_no_token_no_session_404(db_session, captcha_client):
    """Без token и без легаси-сессии -> 404 (нечего решать)."""
    user = await create_user(db_session)
    await db_session.commit()

    async with captcha_client(user.id) as client:
        resp = await client.post("/api/v1/captcha/solve", json={})

    assert resp.status_code == 404


async def test_tokenless_picks_latest_chat_session(db_session, captcha_client):
    """
    Легаси-путь без token: два PENDING chat-сессии одного юзера -> решается САМАЯ
    свежая (ORDER BY created_at DESC), старая остаётся нетронутой.
    """
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    now = datetime.now().astimezone()

    older = await create_captcha_session(db_session, chat.id, user.id, created_at=now - timedelta(minutes=10))
    newer = await create_captcha_session(db_session, chat.id, user.id, created_at=now - timedelta(minutes=1))
    await db_session.commit()

    async with captcha_client(user.id) as client:
        resp = await client.post("/api/v1/captcha/solve", json={})

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "kind": "chat"}

    await db_session.refresh(older)
    await db_session.refresh(newer)
    assert newer.status == CaptchaSessionStatus.PASSED
    assert older.status == CaptchaSessionStatus.PENDING


async def test_tokenless_ignores_join_request_kind(db_session, captcha_client):
    """Легаси-путь фильтрует kind='chat' — PENDING join_request сессия не подходит."""
    chat = await create_chat(db_session)
    user = await create_user(db_session)

    await create_captcha_session(
        db_session,
        chat.id,
        user.id,
        kind=CaptchaSessionKind.JOIN_REQUEST,
        join_request_query_id="query-1",
    )
    await db_session.commit()

    async with captcha_client(user.id) as client:
        resp = await client.post("/api/v1/captcha/solve", json={})

    assert resp.status_code == 404


# ── /solve — kind=join_request (task-9-brief.md) ────────────────────────────────


async def test_solve_join_request_success_approves_via_answer(db_session, captcha_client, monkeypatch):
    """Успешный /solve join_request: claim PASSED -> answer(approve) -> APPROVED + has_passed_captcha."""
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    session_obj = await create_captcha_session(
        db_session,
        chat.id,
        user.id,
        kind=CaptchaSessionKind.JOIN_REQUEST,
        join_request_query_id="q-solve-1",
    )
    await db_session.commit()

    mock_answer = AsyncMock()
    monkeypatch.setattr(captcha_endpoint.bot, "answer_chat_join_request_query", mock_answer)

    async with captcha_client(user.id) as client:
        resp = await client.post("/api/v1/captcha/solve", json={"token": session_obj.token})

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "kind": "join_request"}
    mock_answer.assert_awaited_once_with(chat_join_request_query_id="q-solve-1", result="approve")

    await db_session.refresh(session_obj)
    assert session_obj.status == CaptchaSessionStatus.APPROVED

    await db_session.refresh(user)
    assert user.has_passed_captcha is True


async def test_solve_join_request_bad_request_expires_without_retry(db_session, captcha_client, monkeypatch):
    """Query протух (TelegramBadRequest) -- сессия EXPIRED, 200 с ok=False, без ретрая."""
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    session_obj = await create_captcha_session(
        db_session,
        chat.id,
        user.id,
        kind=CaptchaSessionKind.JOIN_REQUEST,
        join_request_query_id="q-solve-2",
    )
    await db_session.commit()

    bad_request = TelegramBadRequest(method=MagicMock(), message="Bad Request: QUERY_ID_INVALID")
    mock_answer = AsyncMock(side_effect=bad_request)
    monkeypatch.setattr(captcha_endpoint.bot, "answer_chat_join_request_query", mock_answer)

    async with captcha_client(user.id) as client:
        resp = await client.post("/api/v1/captcha/solve", json={"token": session_obj.token})

    assert resp.status_code == 200
    assert resp.json() == {"ok": False, "status": "expired", "kind": "join_request"}
    mock_answer.assert_awaited_once()

    await db_session.refresh(session_obj)
    assert session_obj.status == CaptchaSessionStatus.EXPIRED

    await db_session.refresh(user)
    assert user.has_passed_captcha is False


async def test_solve_transient_error_reverts_to_pending_503(db_session, captcha_client, monkeypatch):
    """TelegramNetworkError на answer -- компенсация: сессия обратно PENDING, HTTP 503, таймаут переиздан."""
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    session_obj = await create_captcha_session(
        db_session,
        chat.id,
        user.id,
        kind=CaptchaSessionKind.JOIN_REQUEST,
        join_request_query_id="q-solve-3",
    )
    await db_session.commit()

    network_error = TelegramNetworkError(method=MagicMock(), message="Network is unreachable")
    mock_answer = AsyncMock(side_effect=[network_error, network_error])
    monkeypatch.setattr(captcha_endpoint.bot, "answer_chat_join_request_query", mock_answer)

    mock_publish = AsyncMock()
    monkeypatch.setattr(captcha_endpoint.broker, "publish", mock_publish)

    async with captcha_client(user.id) as client:
        resp = await client.post("/api/v1/captcha/solve", json={"token": session_obj.token})

    assert resp.status_code == 503
    assert mock_answer.await_count == 2  # одна повторная попытка, потом пробросило

    await db_session.refresh(session_obj)
    assert session_obj.status == CaptchaSessionStatus.PENDING

    await db_session.refresh(user)
    assert user.has_passed_captcha is False

    # компенсация не должна оставить сессию вечным PENDING -- таймаут переиздан, капнутый в 60с
    mock_publish.assert_awaited_once()
    _, publish_kwargs = mock_publish.call_args
    assert publish_kwargs["message"] == {
        "chat_id": chat.id,
        "user_id": user.id,
        "session_id": session_obj.id,
    }
    assert publish_kwargs["routing_key"] == "q.captcha.joinreq_timeout"
    assert publish_kwargs["headers"] == {"x-delay": 60_000}  # expires_at на 5 мин впереди -> капнуто в 60с


async def test_solve_join_request_retry_after_recovers(db_session, captcha_client, monkeypatch):
    """TelegramRetryAfter -- одна повторная попытка после sleep(retry_after), в этот раз успех."""
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    session_obj = await create_captcha_session(
        db_session,
        chat.id,
        user.id,
        kind=CaptchaSessionKind.JOIN_REQUEST,
        join_request_query_id="q-solve-4",
    )
    await db_session.commit()

    retry_error = TelegramRetryAfter(method=MagicMock(), message="Too Many Requests", retry_after=0)
    mock_answer = AsyncMock(side_effect=[retry_error, None])
    monkeypatch.setattr(captcha_endpoint.bot, "answer_chat_join_request_query", mock_answer)

    async with captcha_client(user.id) as client:
        resp = await client.post("/api/v1/captcha/solve", json={"token": session_obj.token})

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "kind": "join_request"}
    assert mock_answer.await_count == 2

    await db_session.refresh(session_obj)
    assert session_obj.status == CaptchaSessionStatus.APPROVED


async def test_solve_join_request_lost_claim_409(db_session, captcha_client):
    """join_request сессия финализирована конкурентно -- 409, Telegram вообще не трогаем."""
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    session_obj = await create_captcha_session(
        db_session,
        chat.id,
        user.id,
        kind=CaptchaSessionKind.JOIN_REQUEST,
        join_request_query_id="q-solve-5",
    )
    await db_session.commit()

    with patch("app.api.v1.endpoints.captcha.claim_session", return_value=False):
        async with captcha_client(user.id) as client:
            resp = await client.post("/api/v1/captcha/solve", json={"token": session_obj.token})

    assert resp.status_code == 409
    assert resp.json()["detail"] == "Session already finalized"


# ── /debug ──────────────────────────────────────────────────────────────────────


async def test_debug_creates_session_with_null_message_id_and_token_url(db_session, captcha_client):
    """create_debug_captcha больше не сеет message_id=0 и возвращает URL с token."""
    admin = await create_user(db_session, is_bot_moderator=True)
    # chat_id=user_id (личка с ботом) -- в проде запись чата уже существует к моменту,
    # когда админ пишет боту команду; создаём её явно, чтобы не упереться в FK.
    await create_chat(db_session, id=admin.id, type="private")
    await db_session.commit()

    async with captcha_client(admin.id) as client:
        resp = await client.post("/api/v1/captcha/debug", json={})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "url" in body

    from sqlalchemy import select

    from app.db.models.captcha_session import ChatCaptchaSession

    result = await db_session.execute(select(ChatCaptchaSession).where(ChatCaptchaSession.id == body["session_id"]))
    captcha_session = result.scalars().one()
    assert captcha_session.message_id is None
    assert captcha_session.token in body["url"]
