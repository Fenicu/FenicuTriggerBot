from pydantic import PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения."""

    POSTGRES_URL: PostgresDsn
    VALKEY_URL: RedisDsn
    BOT_TOKEN: str
    WEBHOOK_PATH: str
    SECRET_TOKEN: str
    TELEGRAM_BOT_API_URL: str | None = None
    RABBITMQ_URL: str = "amqp://guest:guest@rabbitmq:5672/"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_VISION_MODEL: str = "qwen3-vl:8b"
    OLLAMA_TEXT_MODEL: str = "aya-expanse:8b"
    MODERATION_CHANNEL_ID: int

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
