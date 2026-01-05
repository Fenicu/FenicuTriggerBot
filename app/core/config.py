from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, PostgresDsn, RedisDsn, computed_field, field_validator
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
    BOT_ADMINS_STR: str = Field("", alias="BOT_ADMINS")
    BOT_VERSION: str = "unknown"
    BOT_TIMEZONE: str = "Europe/Moscow"

    @computed_field
    def BOT_ADMINS(self) -> list[int]:
        v = self.BOT_ADMINS_STR
        try:
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        except ValueError:
            return []

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
