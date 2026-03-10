from typing import Literal

from pydantic import BaseModel, Field


class ClassifyRequest(BaseModel):
    text: str | None = None
    caption: str | None = None
    image_base64: str | None = None


class ClassifyResponse(BaseModel):
    category: Literal["Drugs", "Porn", "Scam", "Safe"]
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reasoning: str
    source: Literal["nsfw_classifier", "llm"]


class HealthResponse(BaseModel):
    status: str
    nsfw_model_loaded: bool
    ollama_available: bool
