from datetime import datetime

from app.db.models.trigger import AccessLevel, MatchType, ModerationStatus
from pydantic import BaseModel, ConfigDict, Field


class TriggerCreate(BaseModel):
    chat_id: int
    key_phrase: str = Field(min_length=1, max_length=255)
    content: dict
    match_type: MatchType = MatchType.EXACT
    is_case_sensitive: bool = False
    access_level: AccessLevel = AccessLevel.ALL
    is_template: bool = False
    rich: bool = False


class TriggerUpdate(BaseModel):
    key_phrase: str | None = Field(default=None, min_length=1, max_length=255)
    content: dict | None = None
    match_type: MatchType | None = None
    is_case_sensitive: bool | None = None
    access_level: AccessLevel | None = None
    is_template: bool | None = None
    rich: bool | None = None


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
    moderation_category: str | None = None
    moderation_confidence: float | None = None
    is_template: bool
    rich: bool = False
    is_deleted: bool = False
    deleted_at: datetime | None = None
    chat_title: str | None = None
    preview_url: str | None = None
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
    deleted: int = 0
    banned_chat: int = 0
