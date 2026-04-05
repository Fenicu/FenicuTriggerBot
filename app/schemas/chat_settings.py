from pydantic import BaseModel, ConfigDict, field_validator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


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
    welcome_delete_timeout: int

    # Gban
    gban_enabled: bool

    # Trust
    is_trusted: bool

    model_config = ConfigDict(from_attributes=True)


class UpdateChatFullSettingsRequest(BaseModel):
    """Запрос обновления настроек чата (все поля Optional)."""

    # General
    language_code: str | None = None
    timezone: str | None = None

    # Captcha
    captcha_enabled: bool | None = None
    captcha_type: str | None = None
    captcha_timeout: int | None = None
    captcha_max_attempts: int | None = None
    captcha_ban_duration: int | None = None

    # Moderation
    module_moderation: bool | None = None
    warn_limit: int | None = None
    warn_punishment: str | None = None
    warn_duration: int | None = None

    # Triggers
    module_triggers: bool | None = None
    admins_only_add: bool | None = None

    # Tags
    tags_enabled: bool | None = None
    tags_preset: str | None = None
    tags_custom: dict | None = None
    tags_thresholds: list | None = None
    tags_weight_reactions: int | None = None
    tags_weight_replies: int | None = None
    tags_weight_messages: int | None = None
    tags_daily_message_limit: int | None = None
    tags_daily_reaction_limit: int | None = None

    # Welcome
    welcome_enabled: bool | None = None
    welcome_delete_timeout: int | None = None

    # Gban
    gban_enabled: bool | None = None

    # Trust
    is_trusted: bool | None = None

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
                raise ValueError(f"Invalid timezone: {v}")
        return v

    @field_validator("tags_thresholds")
    @classmethod
    def validate_thresholds(cls, v: list | None) -> list | None:
        if v is not None:
            if len(v) != 5 or not all(isinstance(x, int) and x > 0 for x in v):
                raise ValueError("tags_thresholds must be a list of 5 positive integers")
        return v
