from typing import Literal

from pydantic import BaseModel, Field, field_validator


class TriggerModerationTask(BaseModel):
    trigger_id: int
    chat_id: int
    user_id: int
    text_content: str | None = None
    caption: str | None = None
    file_id: str | None = None
    file_type: Literal["photo", "video", "video_note", "animation", "document", "sticker", "voice", "audio"] | None = (
        None
    )


class ModerationLLMResult(BaseModel):
    category: Literal["Drugs", "Porn", "Scam", "Safe"]
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        """Ограничить confidence в диапазоне 0.0-1.0."""
        if isinstance(v, (int, float)):
            return max(0.0, min(1.0, float(v)))
        return v


class ModerationAlert(BaseModel):
    trigger_id: int
    chat_id: int
    category: Literal["Drugs", "Porn", "Scam", "Safe", "Error"]
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reasoning: str | None = None
    image_description: str | None = None


class ModerationHistoryRead(BaseModel):
    """Схема для чтения записи истории модерации."""

    id: int
    trigger_id: int
    step: str
    details: dict | None = None
    actor_id: int | None = None
    created_at: str  # ISO format

    model_config = {"from_attributes": True}


class ModerationHistoryListResponse(BaseModel):
    """Ответ со списком истории модерации."""

    items: list[ModerationHistoryRead]
    current_step: str
