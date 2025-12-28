import base64
import io
import logging

import aiohttp
from app.core.broker import broker
from app.core.config import settings
from app.core.database import engine
from app.core.logging import setup_logging
from app.db.models.trigger import ModerationStatus, Trigger
from app.schemas.moderation import ModerationAlert, ModerationLLMResult, TriggerModerationTask
from faststream import FastStream
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

setup_logging()
logger = logging.getLogger(__name__)

app = FastStream(broker)

# Session maker for worker
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_telegram_file_url(file_id: str) -> str | None:
    """Получить URL файла из Telegram."""
    async with aiohttp.ClientSession() as session:
        url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/getFile?file_id={file_id}"
        if settings.TELEGRAM_BOT_API_URL:
            url = f"{settings.TELEGRAM_BOT_API_URL}/bot{settings.BOT_TOKEN}/getFile?file_id={file_id}"

        async with session.get(url) as response:
            if response.status != 200:
                logger.error(f"Failed to get file info: {response.status}")
                return None
            data = await response.json()
            if not data.get("ok"):
                logger.error(f"Telegram API error: {data}")
                return None

            file_path = data["result"]["file_path"]

            if settings.TELEGRAM_BOT_API_URL:
                return f"{settings.TELEGRAM_BOT_API_URL}/file/bot{settings.BOT_TOKEN}/{file_path}"
            return f"https://api.telegram.org/file/bot{settings.BOT_TOKEN}/{file_path}"


async def download_file(url: str) -> bytes | None:
    """Скачать файл."""
    async with aiohttp.ClientSession() as session, session.get(url) as response:
        if response.status != 200:
            logger.error(f"Failed to download file: {response.status}")
            return None
        return await response.read()


def resize_image(image_data: bytes, max_size: int = 512) -> bytes:
    """Изменить размер изображения, если оно слишком большое."""
    try:
        image = Image.open(io.BytesIO(image_data))

        # Convert to RGB if necessary (e.g. for RGBA or P mode)
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        if max(image.size) > max_size:
            image.thumbnail((max_size, max_size))
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=85)
            return output.getvalue()
        return image_data
    except Exception as e:
        logger.error(f"Failed to resize image: {e}")
        return image_data


async def unload_unknown_models() -> None:
    """Выгрузить модели, которые не используются ботом."""
    known_models = {
        settings.OLLAMA_VISION_MODEL if hasattr(settings, "OLLAMA_VISION_MODEL") else "llava:7b",
        settings.OLLAMA_TEXT_MODEL if hasattr(settings, "OLLAMA_TEXT_MODEL") else "aya-expanse:8b",
    }

    async with aiohttp.ClientSession() as session:
        try:
            # 1. Get running models
            async with session.get(f"{settings.OLLAMA_BASE_URL}/api/ps") as response:
                if response.status != 200:
                    logger.error(f"Failed to list models: {response.status}")
                    return
                data = await response.json()
                running_models = data.get("models", [])

            # 2. Unload unknown models
            for model in running_models:
                model_name = model.get("name")
                # If the running model is NOT in known_models, unload it.
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
    # Resize image to reduce load
    resized_image_data = resize_image(image_data)
    b64_image = base64.b64encode(resized_image_data).decode("utf-8")

    prompt = (
        "Describe this image in detail. Focus on: "
        "- presence of drugs, pills, powders, syringes; "
        "- nudity or sexual content; "
        "- any text visible in the image (e.g. prices, contacts). "
        "Use a concise but detailed natural language description."
    )

    model = settings.OLLAMA_VISION_MODEL if hasattr(settings, "OLLAMA_VISION_MODEL") else "qwen3-vl:8b"

    await unload_unknown_models()

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [b64_image],
        "stream": False,
        "options": {
            "temperature": 0.2,
            "num_predict": 256,
            "top_k": 10,
            "top_p": 0.9,
        },
    }

    async with aiohttp.ClientSession() as session:
        for attempt in range(3):
            try:
                async with session.post(f"{settings.OLLAMA_BASE_URL}/api/generate", json=payload) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Ollama Vision ({model}) error: {response.status}, body: {error_text}")
                        if response.status >= 500:
                            # Retry on server errors
                            continue
                        return ""
                    data = await response.json()
                    result = data.get("response", "")

                    # Check for broken output
                    if "<unk>" in result:
                        logger.warning(f"Ollama returned <unk> tokens: {result}")
                        if attempt < 2:
                            continue
                        return ""

                    return result
            except Exception as e:
                logger.error(f"Failed to call Ollama Vision (attempt {attempt + 1}): {e}")
                if attempt == 2:
                    return ""
    return ""


async def call_moderation_model(text_content: str, caption: str, image_description: str) -> ModerationLLMResult | None:
    """Классифицировать контент с помощью LLM."""

    system_prompt = (
        "You are a content moderation AI. Analyze the provided user content "
        "(text, image caption, and visual description).\n"
        'Classify the content into STRICTLY one of these categories: "Drugs", "Porn", "Scam", or "Safe".\n'
        "Ignore all other types of content.\n\n"
        "Definitions:\n"
        "- Drugs: selling, buying, trading, or promoting illegal drugs or controlled substances.\n"
        "- Porn: explicit nudity, sexual acts, pornographic intent.\n"
        "- Scam: fraud, phishing, attempts to steal money or data, deceptive schemes.\n\n"
        "Output MUST be a valid JSON object with this exact structure:\n"
        "{\n"
        '  "category": "Drugs" | "Porn" | "Scam" | "Safe",\n'
        '  "confidence": float between 0.0 and 1.0,\n'
        '  "reasoning": "short explanation in English"\n'
        "}"
    )

    user_content = (
        f"User Text: {text_content or ''}\n"
        f"Image Caption: {caption or ''}\n"
        f"Image Visual Description: {image_description or ''}"
    )

    model = settings.OLLAMA_TEXT_MODEL if hasattr(settings, "OLLAMA_TEXT_MODEL") else "aya-expanse:8b"

    await unload_unknown_models()

    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.1},
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(f"{settings.OLLAMA_BASE_URL}/api/chat", json=payload) as response:
                if response.status != 200:
                    logger.error(f"Ollama Moderation ({model}) error: {response.status}")
                    return None
                data = await response.json()
                content = data.get("message", {}).get("content", "")

                try:
                    return ModerationLLMResult.model_validate_json(content)
                except Exception as e:
                    logger.error(f"Failed to parse Moderation response: {content}, error: {e}")
                    return None
        except Exception as e:
            logger.error(f"Failed to call Ollama Moderation: {e}")
            return None


async def process_image(task: TriggerModerationTask) -> str:
    """Обработать изображение и получить описание."""
    if not (task.file_id and task.file_type in ["photo", "video", "animation", "document"]):
        return ""

    file_url = await get_telegram_file_url(task.file_id)
    if not file_url:
        return ""

    file_data = await download_file(file_url)
    if not file_data:
        return ""

    # Only send to Vision Model if it's an image.
    if task.file_type == "photo":
        description = await call_vision_model(file_data)
        logger.info(f"Image description: {description}")
        return description

    return ""


async def handle_moderation_result(session: AsyncSession, trigger: Trigger, result: ModerationLLMResult | None) -> None:
    """Обновить статус триггера на основе результата модерации."""
    if not result:
        # Error case
        trigger.moderation_status = ModerationStatus.FLAGGED
        trigger.moderation_reason = "AI Error"
        await session.commit()

        # Send alert
        alert = ModerationAlert(
            trigger_id=trigger.id,
            chat_id=trigger.chat_id,
            category="Error",
            reasoning="AI failed to process",
        )
        await broker.publish(alert, "q.moderation.alerts")
        return

    if result.category == "Safe":
        trigger.moderation_status = ModerationStatus.SAFE
        trigger.moderation_reason = "Safe"
        await session.commit()
        logger.info(f"Trigger {trigger.id} marked as Safe. Reasoning: {result.reasoning}")
    else:
        trigger.moderation_status = ModerationStatus.FLAGGED
        trigger.moderation_reason = result.category
        await session.commit()

        # Publish Alert
        alert = ModerationAlert(
            trigger_id=trigger.id,
            chat_id=trigger.chat_id,
            category=result.category,
            confidence=result.confidence,
            reasoning=result.reasoning,
        )
        await broker.publish(alert, "q.moderation.alerts")
        logger.info(f"Trigger {trigger.id} flagged as {result.category}. Reasoning: {result.reasoning}")


@broker.subscriber("q.moderation.analyze")
async def analyze_trigger(task: TriggerModerationTask) -> None:
    logger.info(f"Analyzing trigger {task.trigger_id} from chat {task.chat_id}")

    # 1. Process Image (if any)
    image_description = await process_image(task)

    # 2. Call Moderation Model
    result = await call_moderation_model(task.text_content, task.caption, image_description)

    # 3. Update Database
    async with async_session() as session:
        trigger = await session.get(Trigger, task.trigger_id)
        if not trigger:
            logger.warning(f"Trigger {task.trigger_id} not found")
            return

        await handle_moderation_result(session, trigger, result)
