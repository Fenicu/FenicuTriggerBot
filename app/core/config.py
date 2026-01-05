from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения."""

    POSTGRES_URL: PostgresDsn
    VALKEY_URL: RedisDsn
    BOT_TOKEN: str
    WEBHOOK_URL: str
    WEBHOOK_PATH: str
    SECRET_TOKEN: str
    TELEGRAM_BOT_API_URL: str | None = None
    RABBITMQ_URL: str = "amqp://guest:guest@rabbitmq:5672/"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_VISION_MODEL: str = "qwen3-vl:8b"
    OLLAMA_TEXT_MODEL: str = "aya-expanse:8b"
    MODERATION_CHANNEL_ID: int
    BOT_ADMINS: list[int] = []
    BOT_VERSION: str = "unknown"
    BOT_TIMEZONE: str = "Europe/Moscow"

    @field_validator("BOT_ADMINS", mode="before")
    @classmethod
    def parse_bot_admins(cls, v: str | list[int]) -> list[int]:
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    @field_validator("BOT_TIMEZONE")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except ZoneInfoNotFoundError:
            raise ValueError(f"Invalid timezone: {v}") from None
        return v

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
