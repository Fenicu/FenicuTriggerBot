from datetime import datetime

from app.db.models.trigger import AccessLevel, MatchType, ModerationStatus
from pydantic import BaseModel, ConfigDict


class TriggerRead(BaseModel):
    id: int
    chat_id: int
    key_phrase: str
    content: dict
    match_type: MatchType
    is_case_sensitive: bool
    access_level: AccessLevel
    usage_count: int
    created_by: int | None
    moderation_status: ModerationStatus
    moderation_reason: str | None
    is_template: bool
    chat_title: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TriggerQueueStatus(BaseModel):
    is_processing: bool


class TriggerListResponse(BaseModel):
    items: list[TriggerRead]
    total: int


class TriggerStatsResponse(BaseModel):
    safe: int = 0
    pending: int = 0
    flagged: int = 0
    banned: int = 0
    error: int = 0
