from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "qwen2.5-vl:7b"
    NSFW_THRESHOLD: float = 0.85
    NSFW_DEVICE: str = "cpu"
    API_KEY: str = ""
    MAX_IMAGE_SIZE: int = 1024

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
