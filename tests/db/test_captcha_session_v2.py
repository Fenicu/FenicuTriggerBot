"""Тесты модели ChatCaptchaSession v2 (state machine) и claim_session."""

import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.captcha_session import (
    CaptchaSessionKind,
    CaptchaSessionStatus,
    ChatCaptchaSession,
    claim_session,
)


async def test_defaults(db_session, base_rows):
    """Новая сессия получает kind=CHAT, status=PENDING, непустой token; message_id пуст."""
    session_obj = ChatCaptchaSession(
        chat_id=-100500,
        user_id=42,
        expires_at=datetime.now().astimezone() + timedelta(minutes=5),
    )
    db_session.add(session_obj)
    await db_session.commit()
    await db_session.refresh(session_obj)

    assert session_obj.kind == CaptchaSessionKind.CHAT
    assert session_obj.status == CaptchaSessionStatus.PENDING
    assert session_obj.message_id is None
    assert session_obj.ephemeral_message_id is None
    assert session_obj.join_request_query_id is None
    assert session_obj.token
    assert len(session_obj.token) >= 20


async def test_claim_transitions_pending_once(db_session, base_rows):
    """claim_session переводит PENDING -> статус один раз; повторный вызов возвращает False."""
    session_obj = ChatCaptchaSession(
        chat_id=-100500,
        user_id=42,
        expires_at=datetime.now().astimezone() + timedelta(minutes=5),
    )
    db_session.add(session_obj)
    await db_session.commit()

    first = await claim_session(db_session, session_obj.id, CaptchaSessionStatus.PASSED)
    second = await claim_session(db_session, session_obj.id, CaptchaSessionStatus.EXPIRED)

    assert first is True
    assert second is False

    await db_session.refresh(session_obj)
    assert session_obj.status == CaptchaSessionStatus.PASSED


async def test_join_request_query_id_unique(db_session, base_rows):
    """join_request_query_id уникален — дубликат query_id падает IntegrityError на commit."""
    expires_at = datetime.now().astimezone() + timedelta(minutes=5)

    db_session.add(
        ChatCaptchaSession(
            chat_id=-100500,
            user_id=42,
            kind=CaptchaSessionKind.JOIN_REQUEST,
            join_request_query_id="query-dup",
            expires_at=expires_at,
        )
    )
    await db_session.commit()

    db_session.add(
        ChatCaptchaSession(
            chat_id=-100500,
            user_id=43,
            kind=CaptchaSessionKind.JOIN_REQUEST,
            join_request_query_id="query-dup",
            expires_at=expires_at,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_concurrent_claims_only_one_wins(_async_engine, base_rows):
    """Два независимых AsyncSession конкурируют за claim -> ровно один True."""
    factory = async_sessionmaker(_async_engine, expire_on_commit=False)
    async with factory() as s1, factory() as s2:
        s = ChatCaptchaSession(
            chat_id=-100500, user_id=42, expires_at=datetime.now().astimezone() + timedelta(minutes=5)
        )
        s1.add(s)
        await s1.commit()
        r1, r2 = await asyncio.gather(
            claim_session(s1, s.id, CaptchaSessionStatus.PASSED),
            claim_session(s2, s.id, CaptchaSessionStatus.EXPIRED),
        )
        assert sorted([r1, r2]) == [False, True]
