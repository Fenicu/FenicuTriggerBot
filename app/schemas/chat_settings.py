from datetime import datetime
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.schemas.message_payload import validate_message_payload
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Section = Literal["general", "captcha", "moderation", "triggers", "tags", "welcome", "other", "autodelete"]
TagLevel = Literal["0", "1", "2", "3", "4", "5"]
TagName = Annotated[str, Field(max_length=16)]
Threshold = Annotated[int, Field(strict=True, ge=1, le=2_147_483_647)]


class AutodeleteTypeConfig(BaseModel):
    enabled: bool = False
    delay: int = Field(default=30, ge=1, le=3600)


class ChatFullSettingsResponse(BaseModel):
    """Полные настройки чата для webapp."""

    # General
    language_code: str
    timezone: str

    # Captcha
    captcha_enabled: bool
    captcha_type: str
    captcha_timeout: int
    captcha_max_attempts: int
    captcha_ban_duration: int

    # Moderation
    module_moderation: bool
    warn_limit: int
    warn_punishment: str
    warn_duration: int

    # Triggers
    module_triggers: bool
    admins_only_add: bool

    # Tags
    tags_enabled: bool
    tags_preset: str
    tags_custom: dict | None = None
    tags_thresholds: list | None = None
    tags_weight_reactions: int
    tags_weight_replies: int
    tags_weight_messages: int
    tags_daily_message_limit: int
    tags_daily_reaction_limit: int

    # Welcome
    welcome_enabled: bool
    welcome_message: dict | None = None

    # Autodelete
    autodelete_settings: dict | None = None

    # Gban
    gban_enabled: bool

    # Trust
    is_trusted: bool

    settings_locked_sections: list | None = None
    is_creator: bool = False  # Will be set dynamically in endpoint

    model_config = ConfigDict(from_attributes=True)


class UpdateChatFullSettingsRequest(BaseModel):
    """Запрос обновления настроек чата (все поля Optional)."""

    # General
    language_code: str | None = Field(default=None, min_length=1, max_length=10)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)

    # Captcha
    captcha_enabled: bool | None = None
    captcha_type: str | None = None
    captcha_timeout: int | None = Field(default=None, ge=60, le=600)
    captcha_max_attempts: int | None = Field(default=None, ge=1, le=10)
    captcha_ban_duration: int | None = Field(default=None, ge=3600, le=604800)

    # Moderation
    module_moderation: bool | None = None
    warn_limit: int | None = Field(default=None, ge=2, le=2147483647)
    warn_punishment: str | None = None
    warn_duration: int | None = Field(default=None, ge=0, le=604800)

    # Triggers
    module_triggers: bool | None = None
    admins_only_add: bool | None = None

    # Tags
    tags_enabled: bool | None = None
    tags_preset: str | None = None
    tags_custom: dict[TagLevel, TagName] | None = Field(default=None, max_length=6)
    tags_thresholds: list[Threshold] | None = Field(default=None, min_length=5, max_length=5)
    tags_weight_reactions: int | None = Field(default=None, ge=0, le=2147483647)
    tags_weight_replies: int | None = Field(default=None, ge=0, le=2147483647)
    tags_weight_messages: int | None = Field(default=None, ge=0, le=2147483647)
    tags_daily_message_limit: int | None = Field(default=None, ge=1, le=2147483647)
    tags_daily_reaction_limit: int | None = Field(default=None, ge=1, le=2147483647)

    # Welcome
    welcome_enabled: bool | None = None
    welcome_message: dict | None = Field(default=None, max_length=64)

    # Autodelete
    autodelete_settings: dict | None = None

    # Gban
    gban_enabled: bool | None = None

    # Trust
    is_trusted: bool | None = None

    settings_locked_sections: list[Section] | None = Field(default=None, max_length=8)

    @model_validator(mode="before")
    @classmethod
    def reject_null_settings(cls, data: Any) -> Any:
        nullable = {
            "tags_custom",
            "tags_thresholds",
            "welcome_message",
            "autodelete_settings",
            "settings_locked_sections",
        }
        if isinstance(data, dict):
            for key, value in data.items():
                if key in cls.model_fields and value is None and key not in nullable:
                    raise ValueError(f"{key} must not be null")
        return data

    @field_validator("warn_punishment")
    @classmethod
    def validate_punishment(cls, v: str | None) -> str | None:
        if v is not None and v not in ("ban", "mute"):
            raise ValueError("warn_punishment must be 'ban' or 'mute'")
        return v

    @field_validator("captcha_type")
    @classmethod
    def validate_captcha_type(cls, v: str | None) -> str | None:
        if v is not None and v not in ("emoji", "webapp"):
            raise ValueError("captcha_type must be 'emoji' or 'webapp'")
        return v

    @field_validator("tags_preset")
    @classmethod
    def validate_tags_preset(cls, v: str | None) -> str | None:
        if v is not None and v not in ("neutral", "gaming", "numeric", "custom"):
            raise ValueError("tags_preset must be 'neutral', 'gaming', 'numeric', or 'custom'")
        return v

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                ZoneInfo(v)
            except (ZoneInfoNotFoundError, KeyError):
                raise ValueError(f"Invalid timezone: {v}") from None
        return v

    @field_validator("tags_thresholds")
    @classmethod
    def validate_thresholds(cls, v: list | None) -> list | None:
        if v is not None and (len(v) != 5 or not all(isinstance(x, int) and x > 0 for x in v)):
            raise ValueError("tags_thresholds must be a list of 5 positive integers")
        return v

    @field_validator("welcome_message")
    @classmethod
    def validate_welcome_message(cls, v: dict | None) -> dict | None:
        if v is None:
            return v
        validate_message_payload(v)
        # story превращается aiogram в ForwardMessage с управляемыми клиентом
        # chat.id/message_id -- так можно переслать контент из чужого чата.
        if "story" in v:
            raise ValueError("Welcome message must not contain story")
        # Must have text or caption or media
        has_text = bool(v.get("text") or v.get("caption"))
        has_media = bool(v.get("photo") or v.get("video") or v.get("animation"))
        has_message_id = bool(v.get("message_id"))  # Legacy format
        if not has_text and not has_media and not has_message_id:
            raise ValueError("Welcome message must have text, media, or be a message copy")
        # Validate buttons if present
        markup = v.get("reply_markup")
        if markup is not None and not isinstance(markup, dict):
            raise ValueError("reply_markup must be an object")
        if markup and markup.get("inline_keyboard"):
            keyboard = markup["inline_keyboard"]
            if not isinstance(keyboard, list) or len(keyboard) > 100:
                raise ValueError("inline_keyboard must be a list of at most 100 rows")
            for row in keyboard:
                if not isinstance(row, list) or len(row) > 3:
                    raise ValueError("Each button row must be a list of max 3 buttons")
                for btn in row:
                    if not isinstance(btn, dict) or "text" not in btn or "url" not in btn:
                        raise ValueError("Each button must have 'text' and 'url'")
        return v

    @field_validator("autodelete_settings")
    @classmethod
    def validate_autodelete(cls, v: dict | None) -> dict | None:
        if v is None:
            return v
        valid_keys = {"captcha_timeout", "captcha_success", "moderation", "gban", "welcome"}
        for key, config in v.items():
            if key not in valid_keys:
                raise ValueError(f"Unknown autodelete type: {key}")
            if not isinstance(config, dict):
                raise ValueError(f"autodelete config for '{key}' must be a dict")
            if "enabled" not in config or not isinstance(config["enabled"], bool):
                raise ValueError(f"autodelete config for '{key}' must have 'enabled' (bool)")
            if "delay" not in config:
                config["delay"] = 30  # normalize: always include delay
            delay = config["delay"]
            if not isinstance(delay, int) or delay < 1 or delay > 3600:
                raise ValueError(f"autodelete delay for '{key}' must be int 1-3600")
        return v


class AuditLogEntry(BaseModel):
    id: int
    chat_id: int
    user_id: int
    section: str
    changes: list
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
