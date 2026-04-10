import base64
import json
import logging
import re

import aiohttp

from app.core.config import settings
from app.schemas.moderation import ModerationLLMResult

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"Drugs", "Porn", "Scam", "Violence", "PersonalData", "Safe"}
JSON_PATTERN = re.compile(r"\{[^{}]*\}", re.DOTALL)

SYSTEM_PROMPT = (
    "You are a Telegram content moderation system. Your task is to classify "
    "user-submitted content (text and/or image) that will be stored as an "
    "automated reply trigger in a Telegram bot.\n\n"
    "Classify into EXACTLY ONE category:\n\n"
    '- "Drugs" — Sale, advertising, or distribution of illegal substances. '
    "Signs: price lists, shop contacts, bot links selling drugs, substance "
    "photos with intent to sell, coded language (❄️ 🍬 🌿 💎), stash/dead-drop "
    'instructions ("клад", "закладка"), graffiti with contacts (@username, URLs). '
    'Russian slang: "мефедрон", "скорость", "шишки", "гашиш", "амфетамин", '
    '"закладки", "кристаллы". Obfuscated: "м3ф", "ск", "a-pvp".\n\n'
    '- "Porn" — Explicit sexual content: genitalia, sexual acts, masturbation, '
    "pornographic links/previews. ESPECIALLY flag any content that may involve "
    "or depict minors (CSAM) — this is the highest-priority violation. "
    "Does NOT include: artistic nudity, medical illustrations, memes without "
    "explicit content.\n\n"
    '- "Scam" — Recruitment for illegal activities or financial fraud. '
    "Signs: \"easy money no experience\", courier/delivery jobs with suspicious "
    "pay, pyramid schemes, fake giveaways, phishing links. "
    'Russian: "работа курьером", "высокий доход без опыта", "лёгкие деньги", '
    '"прогулки по городу", "вакансия кладмен".\n\n'
    '- "Violence" — Threats, extremist content, terrorism propaganda, weapon '
    "sales/trading, graphic violence, calls for violence against individuals "
    "or groups. Signs: weapon photos with price tags, extremist symbols, "
    "beheading/torture imagery, death threats. "
    'Russian: "купить ствол", "заказать", "убью", propaganda channels.\n\n'
    '- "PersonalData" — Leaked personal data: passport scans, ID documents, '
    "database dumps with personal info, doxxing (publishing private addresses, "
    "phone numbers to harass). Signs: photos of documents, spreadsheets with "
    'names+phones+addresses, "слив базы", "пробив по номеру".\n\n'
    '- "Safe" — Everything else. News, discussions, memes, educational content, '
    "opinions, general media, entertainment.\n\n"
    "IMPORTANT RULES:\n"
    "- If an image is provided, analyze BOTH the image and any visible text in it.\n"
    "- Transcribe ALL visible text in images, especially Russian text and slang.\n"
    "- Focus on INTENT: news about drugs ≠ selling drugs. A joke about money ≠ scam.\n"
    "- When uncertain between categories, choose the more dangerous one.\n"
    "- When uncertain between Safe and any violation, lean toward the violation. "
    "False positives go to human review. False negatives risk the bot being deleted.\n\n"
    "Respond in JSON:\n"
    '{"category": "...", "confidence": 0.0-1.0, "reasoning": "explanation in Russian"}'
)


class InferenceUnavailableError(Exception):
    """Raised when inference server is unreachable (retryable)."""


def _build_user_content(text: str, caption: str, image: bytes | None) -> list[dict]:
    """Build OpenAI-format user content with optional image."""
    parts: list[dict] = []

    if image:
        b64 = base64.b64encode(image).decode()
        parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })

    user_text = "Classify this trigger content."
    text_parts = []
    if text:
        text_parts.append(f"Text: {text}")
    if caption:
        text_parts.append(f"Caption: {caption}")
    if text_parts:
        user_text += "\n\n" + "\n".join(text_parts)

    parts.append({"type": "text", "text": user_text})
    return parts


def _parse_result(content: str) -> ModerationLLMResult | None:
    """Parse JSON classification from model response."""
    match = JSON_PATTERN.search(content)
    if not match:
        logger.warning("No JSON in model response: %s", content[:200])
        return None

    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        logger.warning("Invalid JSON in model response: %s", content[:200])
        return None

    category = data.get("category")
    if category not in VALID_CATEGORIES:
        logger.warning("Invalid category '%s' in response", category)
        return None

    confidence = data.get("confidence", 0.5)
    if isinstance(confidence, (int, float)):
        confidence = max(0.0, min(1.0, float(confidence)))
    else:
        confidence = 0.5

    return ModerationLLMResult(
        category=category,
        confidence=confidence,
        reasoning=str(data.get("reasoning", "")),
    )


async def moderate(
    text: str, caption: str, image: bytes | None
) -> ModerationLLMResult | None:
    """Classify content via llama-server OpenAI API.

    Returns ModerationLLMResult on success, None on model error.
    Raises InferenceUnavailableError if server is unreachable.
    """
    url = f"{settings.INFERENCE_URL}/v1/chat/completions"
    payload = {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_content(text, caption, image)},
        ],
        "max_tokens": 256,
        "temperature": 0.1,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=settings.INFERENCE_TIMEOUT)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error("Inference error %d: %s", response.status, error_text[:200])
                    return None

                data = await response.json()
                content = data["choices"][0]["message"]["content"]
                return _parse_result(content)

    except (aiohttp.ClientConnectionError, aiohttp.ServerTimeoutError, OSError) as e:
        logger.warning("Inference server unavailable: %s", e)
        raise InferenceUnavailableError(str(e)) from e
    except Exception as e:
        logger.error("Inference request failed: %s", e)
        return None
