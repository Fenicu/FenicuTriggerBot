from datetime import date

from pydantic import BaseModel


class DailyActivity(BaseModel):
    date: date
    count: int


class StatsResponse(BaseModel):
    total_users: int
    total_chats: int
    active_chats_24h: int
    total_triggers: int
    new_users_last_30_days: list[DailyActivity]
    new_chats_last_30_days: list[DailyActivity]
    message_activity: list[DailyActivity]
    trigger_usage_activity: list[DailyActivity]
