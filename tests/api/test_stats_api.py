"""Tests for /api/v1/stats/ endpoints."""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.daily_stat import DailyStat
from tests.factories import create_chat, create_trigger, create_user


# ---------------------------------------------------------------------------
# GET /stats/
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stats_empty_database(api_client: AsyncClient, db_session: AsyncSession):
    """Stats endpoint returns zeros when the database is empty."""
    resp = await api_client.get("/api/v1/stats/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_users"] == 0
    assert body["total_chats"] == 0
    assert body["total_triggers"] == 0
    assert body["active_chats_24h"] == 0
    assert body["new_users_last_30_days"] == []
    assert body["new_chats_last_30_days"] == []
    assert body["message_activity"] == []
    assert body["trigger_usage_activity"] == []


@pytest.mark.asyncio
async def test_stats_counts_users(api_client: AsyncClient, db_session: AsyncSession):
    await create_user(db_session)
    await create_user(db_session)
    await db_session.commit()

    resp = await api_client.get("/api/v1/stats/")
    assert resp.status_code == 200
    assert resp.json()["total_users"] == 2


@pytest.mark.asyncio
async def test_stats_counts_chats(api_client: AsyncClient, db_session: AsyncSession):
    await create_chat(db_session)
    await create_chat(db_session)
    await create_chat(db_session)
    await db_session.commit()

    resp = await api_client.get("/api/v1/stats/")
    assert resp.status_code == 200
    assert resp.json()["total_chats"] == 3


@pytest.mark.asyncio
async def test_stats_counts_triggers(api_client: AsyncClient, db_session: AsyncSession):
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat.id)
    await create_trigger(db_session, chat.id)
    await db_session.commit()

    resp = await api_client.get("/api/v1/stats/")
    assert resp.status_code == 200
    assert resp.json()["total_triggers"] == 2


@pytest.mark.asyncio
async def test_stats_active_chats_24h(api_client: AsyncClient, db_session: AsyncSession):
    """Chats updated recently should appear in active_chats_24h."""
    # create_chat sets updated_at via server_default=func.now(), so it counts as "active".
    await create_chat(db_session)
    await db_session.commit()

    resp = await api_client.get("/api/v1/stats/")
    assert resp.status_code == 200
    assert resp.json()["active_chats_24h"] >= 1


@pytest.mark.asyncio
async def test_stats_new_users_graph(api_client: AsyncClient, db_session: AsyncSession):
    """Users created today should appear in the new_users_last_30_days graph."""
    await create_user(db_session)
    await db_session.commit()

    resp = await api_client.get("/api/v1/stats/")
    assert resp.status_code == 200
    data = resp.json()["new_users_last_30_days"]
    assert len(data) >= 1
    # Use UTC date since server_default=func.now() uses DB server time (UTC)
    from datetime import datetime, timezone

    today_str = datetime.now(timezone.utc).date().isoformat()
    assert any(entry["date"] == today_str for entry in data)


@pytest.mark.asyncio
async def test_stats_new_chats_graph(api_client: AsyncClient, db_session: AsyncSession):
    """Chats created today should appear in the new_chats_last_30_days graph."""
    await create_chat(db_session)
    await db_session.commit()

    resp = await api_client.get("/api/v1/stats/")
    assert resp.status_code == 200
    data = resp.json()["new_chats_last_30_days"]
    assert len(data) >= 1


@pytest.mark.asyncio
async def test_stats_daily_stats_message_activity(api_client: AsyncClient, db_session: AsyncSession):
    """DailyStat records should populate message_activity."""
    today = date.today()
    stat = DailyStat(date=today, messages_count=42, triggers_count=7)
    db_session.add(stat)
    await db_session.commit()

    resp = await api_client.get("/api/v1/stats/")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["message_activity"]) == 1
    assert body["message_activity"][0]["count"] == 42
    assert body["trigger_usage_activity"][0]["count"] == 7


@pytest.mark.asyncio
async def test_stats_daily_stats_outside_30_days_excluded(api_client: AsyncClient, db_session: AsyncSession):
    """DailyStat records older than 30 days should not appear."""
    old_date = date.today() - timedelta(days=60)
    stat = DailyStat(date=old_date, messages_count=100, triggers_count=50)
    db_session.add(stat)
    await db_session.commit()

    resp = await api_client.get("/api/v1/stats/")
    assert resp.status_code == 200
    assert resp.json()["message_activity"] == []
    assert resp.json()["trigger_usage_activity"] == []


@pytest.mark.asyncio
async def test_stats_no_auth_required(api_client: AsyncClient):
    """Stats endpoint should be accessible without authentication."""
    resp = await api_client.get("/api/v1/stats/")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_stats_response_shape(api_client: AsyncClient, db_session: AsyncSession):
    """Verify the response contains all expected top-level keys."""
    resp = await api_client.get("/api/v1/stats/")
    assert resp.status_code == 200
    body = resp.json()
    expected_keys = {
        "total_users",
        "total_chats",
        "active_chats_24h",
        "total_triggers",
        "new_users_last_30_days",
        "new_chats_last_30_days",
        "message_activity",
        "trigger_usage_activity",
    }
    assert expected_keys == set(body.keys())


@pytest.mark.asyncio
async def test_stats_multiple_daily_stats(api_client: AsyncClient, db_session: AsyncSession):
    """Multiple DailyStat entries should all appear sorted."""
    today = date.today()
    for i in range(3):
        d = today - timedelta(days=i)
        stat = DailyStat(date=d, messages_count=10 * (i + 1), triggers_count=i)
        db_session.add(stat)
    await db_session.commit()

    resp = await api_client.get("/api/v1/stats/")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["message_activity"]) == 3
    # Should be sorted by date ascending
    dates = [entry["date"] for entry in body["message_activity"]]
    assert dates == sorted(dates)
