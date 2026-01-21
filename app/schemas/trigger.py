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
    created_by: int
    moderation_status: ModerationStatus
    moderation_reason: str | None
    is_template: bool

    model_config = ConfigDict(from_attributes=True)


class TriggerQueueStatus(BaseModel):
    is_processing: bool


class TriggerListResponse(BaseModel):
    items: list[TriggerRead]
    total: int
