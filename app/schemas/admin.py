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
    is_bot_moderator: bool
    is_trusted: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatResponse(BaseModel):
    id: int
    admins_only_add: bool
    language_code: str
    warn_limit: int
    warn_punishment: str
    warn_duration: int
    is_trusted: bool
    created_at: datetime
    is_banned: bool = False
    ban_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class UpdateUserRoleRequest(BaseModel):
    is_trusted: bool | None = None
    is_bot_moderator: bool | None = None


class BanChatRequest(BaseModel):
    reason: str


class SendMessageRequest(BaseModel):
    text: str
