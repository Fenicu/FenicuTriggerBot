import base64
import logging

import aiohttp
from app.core.config import settings
from app.schemas.moderation import ModerationLLMResult

logger = logging.getLogger(__name__)


async def classify_content(
    text: str | None = None,
    caption: str | None = None,
    image_data: bytes | None = None,
) -> ModerationLLMResult | None:
    """Send content to inference server for classification."""
    payload: dict = {}
    if text:
        payload["text"] = text
    if caption:
        payload["caption"] = caption
    if image_data:
        payload["image_base64"] = base64.b64encode(image_data).decode("utf-8")

    if not payload:
        return ModerationLLMResult(category="Safe", confidence=None, reasoning="No content", source="llm")

    headers: dict[str, str] = {}
    if settings.INFERENCE_API_KEY:
        headers["X-API-Key"] = settings.INFERENCE_API_KEY

    timeout = aiohttp.ClientTimeout(total=settings.INFERENCE_TIMEOUT)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session, session.post(
            f"{settings.INFERENCE_URL}/classify",
            json=payload,
            headers=headers,
        ) as response:
            if response.status == 503:
                logger.error("Inference server: LLM unavailable")
                return None
            if response.status != 200:
                error = await response.text()
                logger.error(f"Inference server error: {response.status}, body: {error}")
                return None

            data = await response.json()
            return ModerationLLMResult.model_validate(data)
    except TimeoutError:
        logger.error("Inference server timeout")
        return None
    except Exception:
        logger.exception("Failed to call inference server")
        return None
