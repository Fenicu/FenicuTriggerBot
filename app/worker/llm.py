import base64
import logging

import aiohttp
from app.core.config import settings
from app.schemas.moderation import ModerationLLMResult
from app.worker.image import resize_image

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


async def unload_unknown_models() -> None:
    """Выгрузить модели, которые не используются ботом."""
    known_models = {
        settings.OLLAMA_VISION_MODEL,
        settings.OLLAMA_TEXT_MODEL,
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"{settings.OLLAMA_BASE_URL}/api/ps") as response:
                if response.status != 200:
                    logger.error(f"Failed to list models: {response.status}")
                    return
                data = await response.json()
                running_models = data.get("models", [])

            for model in running_models:
                model_name = model.get("name")
                if model_name not in known_models:
                    logger.info(f"Unloading unknown model: {model_name}")
                    unload_payload = {"model": model_name, "keep_alive": 0}
                    async with session.post(
                        f"{settings.OLLAMA_BASE_URL}/api/generate", json=unload_payload
                    ) as unload_response:
                        if unload_response.status != 200:
                            logger.error(f"Failed to unload model {model_name}: {unload_response.status}")
        except Exception as e:
            logger.error(f"Failed to manage models: {e}")


async def call_vision_model(image_data: bytes) -> str:
    """Получить описание изображения от Vision модели."""
    resized_image_data = resize_image(image_data)
    b64_image = base64.b64encode(resized_image_data).decode("utf-8")

    prompt = (
        "Analyze this image strictly for content moderation. Provide a detailed objective description. "
        "Focus your attention on these specific risk indicators:\n\n"
        "1. DRUG TRADE SIGNS:\n"
        "   - Substances: Powders, crystals, pills, cannabis buds.\n"
        "   - Paraphernalia: Syringes, precision scales, bongs, glass pipes.\n"
        "   - Packaging: Small ziplock bags, bundles wrapped in colored electrical tape or foil (typical for 'dead drops/klads'), magnetic boxes.\n\n"  # noqa: E501
        "2. RECRUITMENT & ADVERTISING (SCAM):\n"
        "   - Street Graffiti/Stencils: Look for spray-painted text on walls/pavements containing @usernames, URLs, or keywords like 'rabota', 'sk', 'shish', 'z.', 'zp'.\n"  # noqa: E501
        "   - Screenshots: Text conversations about 'easy money', 'deliveries', or 'walking jobs'.\n"
        "   - QR Codes: Any visible QR codes or barcodes.\n\n"
        "3. PORNOGRAPHY:\n"
        "   - Explicit nudity, genitalia, sexual acts, or highly suggestive poses.\n\n"
        "CRITICAL INSTRUCTION: Transcribe ALL visible text verbatim, especially text overlays, "
        "handwritten notes, or graffiti. If text is in Russian or slang, transcribe it exactly as is."
    )

    await unload_unknown_models()

    payload = {
        "model": settings.OLLAMA_VISION_MODEL,
        "prompt": prompt,
        "images": [b64_image],
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 512,
            "top_k": 10,
            "top_p": 0.9,
        },
    }

    async with aiohttp.ClientSession() as session:
        for attempt in range(MAX_RETRIES):
            try:
                async with session.post(f"{settings.OLLAMA_BASE_URL}/api/generate", json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(
                            f"Ollama Vision ({settings.OLLAMA_VISION_MODEL}) "
                            f"error: {response.status}, body: {error_text}"
                        )
                        if response.status >= 500:
                            continue
                        return ""
                    data: dict = await response.json()
                    result = data.get("response", "")

                    if "<unk>" in result:
                        logger.warning(f"Ollama returned <unk> tokens: {result}")
                        if attempt < MAX_RETRIES - 1:
                            continue
                        return ""

                    return result
            except Exception as e:
                logger.error(f"Failed to call Ollama Vision (attempt {attempt + 1}): {e}")
                if attempt == MAX_RETRIES - 1:
                    return ""
    return ""


async def call_moderation_model(text_content: str, caption: str, image_description: str) -> ModerationLLMResult | None:
    """Классифицировать контент с помощью LLM."""

    system_prompt = (
        "You are a specialized content moderation AI. Analyze the provided user content "
        "(text, image caption, and visual description) to detect illegal goods and recruitment.\n"
        "Your goal is to classify content into STRICTLY one of these categories: "
        '"Drugs", "Porn", "Scam", or "Safe".\n\n'
        "Priority Instructions:\n"
        "1. Look for obfuscated language, emojis (e.g., ❄️, 🍬, 🌿), and slang used in drug trade.\n"
        "2. Differentiate between general spam and specific recruitment for illegal work.\n\n"
        "Definitions for Classification:\n"
        "🔴 Drugs: Content related to the DIRECT SALE, advertising, or promotion of illegal substances.\n"
        "   - Includes: Price lists, 'shop' links, photos of substances with intent to sell, specific strain names/prices.\n"  # noqa: E501
        "   - Excludes: News, educational, or scientific discussion about drugs without promotion.\n\n"
        "🔞 Porn: Explicit sexual content.\n"
        "   - Includes: Visible genitalia, sexual acts, masturbation, pornographic intent/links.\n"
        "   - Excludes: Artistic nudity (statues), medical context (unless explicit).\n\n"
        "⚠️ Scam (Drug Recruitment Focus): Content recruiting people for illegal distribution roles.\n"
        "   - Keywords/Concepts: 'High salary no experience', 'courier', 'delivery job', 'easy money', 'graffiti job', "
        "'warehouse worker', 'walking around the city'.\n"
        "   - Focus: Job offers that imply becoming a 'dropper' (kladmen) or money mule.\n\n"
        "✅ Safe: Content that clearly does NOT fit the above categories.\n\n"
        "Output MUST be a valid JSON object with this exact structure:\n"
        "{\n"
        '  "category": "Drugs" | "Porn" | "Scam" | "Safe",\n'
        '  "confidence": float between 0.0 and 1.0,\n'
        '  "reasoning": "short explanation in Russian focusing on detected keywords or visual cues"\n'
        "}"
    )

    user_content = (
        f"User Text: {text_content or 'No text provided'}\n"
        f"Image Caption: {caption or 'No caption'}\n"
        f"Image Visual Description: {image_description or 'No image'}"
    )

    await unload_unknown_models()

    payload = {
        "model": settings.OLLAMA_TEXT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.1},
    }

    async with aiohttp.ClientSession() as session:
        for attempt in range(MAX_RETRIES):
            try:
                async with session.post(f"{settings.OLLAMA_BASE_URL}/api/chat", json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(
                            f"Ollama Moderation ({settings.OLLAMA_TEXT_MODEL}) "
                            f"error: {response.status}, body: {error_text}"
                        )
                        if response.status >= 500:
                            continue
                        return None
                    data: dict = await response.json()
                    content = data.get("message", {}).get("content", "")

                    try:
                        return ModerationLLMResult.model_validate_json(content)
                    except Exception as e:
                        logger.error(
                            f"Failed to parse Moderation response (attempt {attempt + 1}): {content}, error: {e}"
                        )
                        if attempt < MAX_RETRIES - 1:
                            continue
                        return None
            except Exception as e:
                logger.error(f"Failed to call Ollama Moderation (attempt {attempt + 1}): {e}")
                if attempt == MAX_RETRIES - 1:
                    return None
        return None
