from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db.models.chat import Chat
from app.db.models.daily_stat import DailyStat
from app.db.models.trigger import Trigger
from app.db.models.user import User
from app.schemas.stats import DailyActivity, StatsResponse

router = APIRouter()


@router.get("", response_model=StatsResponse)
async def get_stats(
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    """
    Получить статистику по боту.
    """
    # Total counts
    total_users = await db.scalar(select(func.count(User.id)))
    total_chats = await db.scalar(select(func.count(Chat.id)))
    total_triggers = await db.scalar(select(func.count(Trigger.id)))

    # Active chats in last 24h
    yesterday = datetime.now(UTC) - timedelta(days=1)
    active_chats_24h = await db.scalar(select(func.count(Chat.id)).where(Chat.updated_at >= yesterday))

    # Graphs: Last 30 days
    thirty_days_ago = datetime.now(UTC) - timedelta(days=30)

    # New Users
    users_query = (
        select(func.date(User.created_at).label("date"), func.count(User.id).label("count"))
        .where(User.created_at >= thirty_days_ago)
        .group_by(func.date(User.created_at))
        .order_by(func.date(User.created_at))
    )
    users_result = await db.execute(users_query)
    new_users_data = [DailyActivity(date=row.date, count=row.count) for row in users_result]

    # New Chats
    chats_query = (
        select(func.date(Chat.created_at).label("date"), func.count(Chat.id).label("count"))
        .where(Chat.created_at >= thirty_days_ago)
        .group_by(func.date(Chat.created_at))
        .order_by(func.date(Chat.created_at))
    )
    chats_result = await db.execute(chats_query)
    new_chats_data = [DailyActivity(date=row.date, count=row.count) for row in chats_result]

    # Daily Stats
    stats_query = select(DailyStat).where(DailyStat.date >= thirty_days_ago).order_by(DailyStat.date)
    stats_result = await db.execute(stats_query)
    daily_stats = stats_result.scalars().all()

    message_activity = [DailyActivity(date=s.date, count=s.messages_count) for s in daily_stats]
    trigger_usage_activity = [DailyActivity(date=s.date, count=s.triggers_count) for s in daily_stats]

    return StatsResponse(
        total_users=total_users or 0,
        total_chats=total_chats or 0,
        active_chats_24h=active_chats_24h or 0,
        total_triggers=total_triggers or 0,
        new_users_last_30_days=new_users_data,
        new_chats_last_30_days=new_chats_data,
        message_activity=message_activity,
        trigger_usage_activity=trigger_usage_activity,
    )
