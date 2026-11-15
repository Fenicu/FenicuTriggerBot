"""Суточная статистика: счётчики копятся в Valkey и периодически сбрасываются в DailyStat."""

import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.daily_stat import DailyStat
from app.services import daily_stats_service, trigger_service
from tests.factories import create_chat, create_trigger


@pytest.fixture(autouse=True)
def _real_valkey(valkey_client):
    with patch("app.services.daily_stats_service.valkey", valkey_client):
        yield valkey_client


@pytest.fixture
def session_factory(_async_engine):
    return async_sessionmaker(_async_engine, expire_on_commit=False)


async def _stats(db_session) -> dict[date, DailyStat]:
    db_session.expire_all()
    rows = (await db_session.execute(select(DailyStat))).scalars().all()
    return {row.date: row for row in rows}


async def test_count_does_not_touch_database(db_session, valkey_client):
    await daily_stats_service.count_message()
    await daily_stats_service.count_message()
    await daily_stats_service.count_trigger_usage()

    assert await _stats(db_session) == {}
    pending = await valkey_client.hgetall(daily_stats_service.PENDING_KEY)
    today = date.today().isoformat()
    assert pending == {f"{today}:messages_count": "2", f"{today}:triggers_count": "1"}


async def test_flush_moves_counters_to_daily_stat(db_session, session_factory, valkey_client):
    for _ in range(3):
        await daily_stats_service.count_message()
    await daily_stats_service.count_trigger_usage()

    await daily_stats_service.flush_daily_stats(session_factory)

    stat = (await _stats(db_session))[date.today()]
    assert (stat.messages_count, stat.triggers_count) == (3, 1)
    assert await valkey_client.exists(daily_stats_service.PENDING_KEY) == 0


async def test_flush_twice_does_not_double_count(db_session, session_factory):
    await daily_stats_service.count_message()

    await daily_stats_service.flush_daily_stats(session_factory)
    await daily_stats_service.flush_daily_stats(session_factory)

    assert (await _stats(db_session))[date.today()].messages_count == 1


async def test_flush_adds_to_existing_row(db_session, session_factory):
    db_session.add(DailyStat(date=date.today(), messages_count=10, triggers_count=5))
    await db_session.commit()
    await daily_stats_service.count_message()
    await daily_stats_service.count_trigger_usage()

    await daily_stats_service.flush_daily_stats(session_factory)

    stat = (await _stats(db_session))[date.today()]
    assert (stat.messages_count, stat.triggers_count) == (11, 6)


async def test_flush_keeps_counters_of_previous_day(db_session, session_factory, valkey_client):
    """Счётчики, накопленные до полуночи, попадают в строку своего дня."""
    yesterday = date.today() - timedelta(days=1)
    await valkey_client.hincrby(daily_stats_service.PENDING_KEY, f"{yesterday.isoformat()}:messages_count", 7)
    await daily_stats_service.count_message()

    await daily_stats_service.flush_daily_stats(session_factory)

    stats = await _stats(db_session)
    assert stats[yesterday].messages_count == 7
    assert stats[date.today()].messages_count == 1


async def test_flush_restores_counters_when_database_fails(valkey_client):
    await daily_stats_service.count_message()
    await daily_stats_service.count_message()

    broken_factory = MagicMock(side_effect=RuntimeError("db down"))
    with pytest.raises(RuntimeError):
        await daily_stats_service.flush_daily_stats(broken_factory)

    pending = await valkey_client.hgetall(daily_stats_service.PENDING_KEY)
    assert pending == {f"{date.today().isoformat()}:messages_count": "2"}


async def test_count_survives_valkey_failure():
    broken = MagicMock()
    broken.hincrby = AsyncMock(side_effect=ConnectionError("down"))
    with patch("app.services.daily_stats_service.valkey", broken):
        await daily_stats_service.count_message()


async def test_stats_middleware_counts_in_valkey_without_db_write(valkey_client):
    from app.bot.middlewares.stats import StatsMiddleware

    session = AsyncMock()
    handler = AsyncMock(return_value="ok")

    result = await StatsMiddleware()(handler, MagicMock(spec=Message), {"session": session})

    assert result == "ok"
    session.execute.assert_not_awaited()
    session.commit.assert_not_awaited()
    pending = await valkey_client.hgetall(daily_stats_service.PENDING_KEY)
    assert pending == {f"{date.today().isoformat()}:messages_count": "1"}


async def test_stats_middleware_skips_non_message(valkey_client):
    from app.bot.middlewares.stats import StatsMiddleware

    await StatsMiddleware()(AsyncMock(), MagicMock(), {"session": AsyncMock()})

    assert await valkey_client.exists(daily_stats_service.PENDING_KEY) == 0


async def test_increment_usage_counts_in_valkey_not_daily_stat(db_session, valkey_client):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id)
    await db_session.commit()

    await trigger_service.increment_usage(db_session, trigger.id)

    await db_session.refresh(trigger)
    assert trigger.usage_count == 1
    assert await _stats(db_session) == {}
    pending = await valkey_client.hgetall(daily_stats_service.PENDING_KEY)
    assert pending == {f"{date.today().isoformat()}:triggers_count": "1"}


async def test_flush_loop_survives_flush_errors():
    """Ошибка одного сброса не останавливает фоновую задачу."""
    calls = 0

    async def flaky_flush() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        raise asyncio.CancelledError

    with (
        patch.object(daily_stats_service, "flush_daily_stats", flaky_flush),
        patch.object(daily_stats_service.asyncio, "sleep", AsyncMock()),
        pytest.raises(asyncio.CancelledError),
    ):
        await daily_stats_service.run_flush_loop(interval=0)

    assert calls == 2
