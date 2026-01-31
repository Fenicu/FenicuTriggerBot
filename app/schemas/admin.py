from datetime import datetime
from typing import TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class Pagination(BaseModel):
    page: int
    limit: int
    total: int
    total_pages: int


class PaginatedResponse[T](BaseModel):
    items: list[T]
    pagination: Pagination


class UserResponse(BaseModel):
    id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None
    is_premium: bool | None = None
    photo_id: str | None = None
    is_bot: bool = False
    is_bot_moderator: bool
    is_trusted: bool
    is_gban: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatResponse(BaseModel):
    id: int
    title: str | None = None
    username: str | None = None
    type: str | None = None
    description: str | None = None
    invite_link: str | None = None
    photo_id: str | None = None
    admins_only_add: bool
    language_code: str
    warn_limit: int
    warn_punishment: str
    warn_duration: int
    is_trusted: bool
    is_active: bool
    timezone: str
    module_triggers: bool
    module_moderation: bool
    created_at: datetime
    is_banned: bool = False
    ban_reason: str | None = None
    triggers_count: int = 0
    users_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class UpdateUserRoleRequest(BaseModel):
    is_trusted: bool | None = None
    is_bot_moderator: bool | None = None


class BanChatRequest(BaseModel):
    reason: str


class SendMessageRequest(BaseModel):
    text: str


class UpdateChatSettingsRequest(BaseModel):
    timezone: str | None = None
    module_triggers: bool | None = None
    module_moderation: bool | None = None


class TriggerResponse(BaseModel):
    id: int
    chat_id: int
    key_phrase: str
    content: dict
    match_type: str
    is_case_sensitive: bool
    access_level: str
    usage_count: int
    created_by: int
    moderation_status: str
    moderation_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserChatResponse(BaseModel):
    chat: ChatResponse
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatUserResponse(BaseModel):
    user: UserResponse
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
