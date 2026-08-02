from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения."""

    POSTGRES_URL: PostgresDsn
    VALKEY_URL: RedisDsn
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: SecretStr
    S3_ENDPOINT: str = "rustfs:9000"
    S3_BUCKET: str = "trigger-cache"
    S3_SECURE: bool = False
    BOT_TOKEN: str
    WEBAPP_URL: str
    MINIAPP_SHORT_NAME: str = ""
    WEBHOOK_URL: str
    WEBHOOK_PATH: str
    SECRET_TOKEN: str
    TELEGRAM_BOT_API_URL: str | None = None
    RABBITMQ_URL: str = "amqp://guest:guest@rabbitmq:5672/"
    INFERENCE_URL: str = "http://10.10.40.24:8090"
    INFERENCE_TIMEOUT: int = 600
    INFERENCE_STALE_ALERT_TIMEOUT: int = 300
    MODERATION_FAIL_BACKOFF_SECONDS: int = 300
    MODERATION_MAX_ATTEMPTS: int = 5
    MODERATION_STUCK_AFTER_MINUTES: int = 20
    ASR_URL: str = "http://10.10.40.24:8091"
    ASR_TOKEN: SecretStr = SecretStr("")
    ASR_TIMEOUT: int = 120
    ASR_ENABLED: bool = True
    MODERATION_CHANNEL_ID: int
    BOT_ADMINS_STR: str = Field("", alias="BOT_ADMINS")
    BOT_VERSION: str = "unknown"
    BOT_TIMEZONE: str = "Europe/Moscow"
    API_V1_STR: str = "/api/v1"
    URL_PREFIX: str = ""
    GBAN_LIST_URL: str = "https://lols.bot/spam/banlist.json"
    SENTRY_DSN: str | None = None

    # Link analysis
    LINK_ANALYSIS_ENABLED: bool = True
    LINK_FETCH_TIMEOUT: int = 5
    LINK_FETCH_MAX_BYTES: int = 512 * 1024
    LINK_FETCH_MAX_LINKS: int = 3
    LINK_FETCH_MAX_REDIRECTS: int = 5

    # Chat trust automation
    TRUST_AUTO_ENABLED: bool = True
    TRUST_AUTO_STREAK_THRESHOLD: int = 20
    TRUST_AUTO_FALSE_POSITIVE_THRESHOLD: int = 3

    # Telegram OIDC
    TELEGRAM_OIDC_CLIENT_ID: str = ""
    TELEGRAM_OIDC_CLIENT_SECRET: str = ""
    TELEGRAM_OIDC_REDIRECT_URI: str = ""
    SESSION_SECRET_KEY: str = ""

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
