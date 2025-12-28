from typing import Literal

from pydantic import BaseModel


class TriggerModerationTask(BaseModel):
    trigger_id: int
    chat_id: int
    user_id: int
    text_content: str | None = None
    caption: str | None = None
    file_id: str | None = None
    file_type: Literal["photo", "video", "animation", "document"] | None = None


class ModerationLLMResult(BaseModel):
    category: Literal["Drugs", "Porn", "Scam", "Safe"]
    confidence: float
    reasoning: str


class ModerationAlert(BaseModel):
    trigger_id: int
    chat_id: int
    category: Literal["Drugs", "Porn", "Scam", "Safe", "Error"]
    confidence: float | None = None
    reasoning: str | None = None
