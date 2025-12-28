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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
