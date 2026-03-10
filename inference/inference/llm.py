import base64
import json
import logging

import aiohttp

from inference.config import settings
from inference.image import resize_image
from inference.schemas import ClassifyResponse

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
TIMEOUT = aiohttp.ClientTimeout(total=120)

SYSTEM_PROMPT = (
    "You are a content moderation AI. Analyze the provided content (text and/or image) "
    "to detect illegal goods trading, recruitment for illegal work, or explicit sexual content.\n\n"
    "Classify into STRICTLY one category:\n"
    '- "Drugs": Direct sale, advertising, or promotion of illegal substances. '
    "Includes price lists, shop links, photos of substances with intent to sell.\n"
    '- "Scam": Recruitment for illegal distribution roles (droppers/couriers). '
    "Keywords: easy money, courier job, high salary no experience, graffiti job.\n"
    '- "Porn": Explicit sexual content — visible genitalia, sexual acts.\n'
    '- "Safe": Content that does NOT fit the above categories.\n\n'
    "Return ONLY a valid JSON object:\n"
    '{"category": "Drugs"|"Porn"|"Scam"|"Safe", "reasoning": "short explanation in Russian"}\n'
    "You MUST make a decision. Do not return empty objects."
)


async def check_ollama_health() -> bool:
    """Check if Ollama is available."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(f"{settings.OLLAMA_BASE_URL}/api/tags") as resp:
                return resp.status == 200
    except Exception:
        return False


async def classify_with_llm(
    text: str | None = None,
    caption: str | None = None,
    image_data: bytes | None = None,
) -> ClassifyResponse | None:
    """Classify content using multimodal LLM."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    user_parts = []
    if text:
        user_parts.append(f"Text: {text}")
    if caption:
        user_parts.append(f"Caption: {caption}")
    if not user_parts:
        user_parts.append("No text provided. Analyze the image only.")

    user_content = "\n".join(user_parts)

    user_message: dict = {"role": "user", "content": user_content}
    if image_data:
        resized = resize_image(image_data)
        b64 = base64.b64encode(resized).decode("utf-8")
        user_message["images"] = [b64]

    messages.append(user_message)

    payload = {
        "model": settings.OLLAMA_MODEL,
        "messages": messages,
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.1},
    }

    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        for attempt in range(MAX_RETRIES):
            try:
                async with session.post(
                    f"{settings.OLLAMA_BASE_URL}/api/chat",
                    json=payload,
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Ollama error: {response.status}, body: {error_text}")
                        if response.status >= 500:
                            continue
                        return None

                    data = await response.json()
                    content = data.get("message", {}).get("content", "")

                    if not content or content == "{}":
                        logger.warning(f"Ollama returned empty content (attempt {attempt + 1})")
                        continue

                    try:
                        parsed = json.loads(content)
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse JSON (attempt {attempt + 1}): {content}")
                        continue

                    category = parsed.get("category", "Safe")
                    if category not in ("Drugs", "Porn", "Scam", "Safe"):
                        category = "Safe"

                    return ClassifyResponse(
                        category=category,
                        confidence=None,
                        reasoning=parsed.get("reasoning", "No reasoning provided"),
                        source="llm",
                    )
            except TimeoutError:
                logger.error(f"Ollama timeout (attempt {attempt + 1})")
            except Exception:
                logger.exception(f"Ollama error (attempt {attempt + 1})")

    return None
