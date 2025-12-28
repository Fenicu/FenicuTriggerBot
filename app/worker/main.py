import base64
import logging

import aiohttp
from app.core.broker import broker
from app.core.config import settings
from app.core.database import engine
from app.core.logging import setup_logging
from app.db.models.trigger import ModerationStatus, Trigger
from app.schemas.moderation import ModerationAlert, ModerationLLMResult, TriggerModerationTask
from faststream import FastStream
from sqlalchemy.ext.asyncio import async_sessionmaker

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


async def call_ollama_llava(image_data: bytes) -> str:
    """Получить описание изображения от LLaVA."""
    b64_image = base64.b64encode(image_data).decode("utf-8")

    prompt = (
        "Describe this image in detail. Focus on: "
        "- presence of drugs, pills, powders, syringes; "
        "- nudity or sexual content; "
        "- any text visible in the image (e.g. prices, contacts). "
        "Use a concise but detailed natural language description."
    )

    payload = {"model": "llava:7b", "prompt": prompt, "images": [b64_image], "stream": False}

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(f"{settings.OLLAMA_BASE_URL}/api/generate", json=payload) as response:
                if response.status != 200:
                    logger.error(f"Ollama LLaVA error: {response.status}")
                    return ""
                data = await response.json()
                return data.get("response", "")
        except Exception as e:
            logger.error(f"Failed to call Ollama LLaVA: {e}")
            return ""


async def call_ollama_aya(text_content: str, caption: str, image_description: str) -> ModerationLLMResult | None:
    """Классифицировать контент с помощью Aya Expanse."""

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

    payload = {
        "model": "aya-expanse:8b",
        "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.1},
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(f"{settings.OLLAMA_BASE_URL}/api/chat", json=payload) as response:
                if response.status != 200:
                    logger.error(f"Ollama Aya error: {response.status}")
                    return None
                data = await response.json()
                content = data.get("message", {}).get("content", "")

                try:
                    return ModerationLLMResult.model_validate_json(content)
                except Exception as e:
                    logger.error(f"Failed to parse Aya response: {content}, error: {e}")
                    return None
        except Exception as e:
            logger.error(f"Failed to call Ollama Aya: {e}")
            return None


@broker.subscriber("q.moderation.analyze")
async def analyze_trigger(task: TriggerModerationTask) -> None:
    logger.info(f"Analyzing trigger {task.trigger_id} from chat {task.chat_id}")

    image_description = ""

    # 1. Handle Image
    if task.file_id and task.file_type in ["photo", "video", "animation", "document"]:
        file_url = await get_telegram_file_url(task.file_id)
        if file_url:
            file_data = await download_file(file_url)
            # Only send to LLaVA if it's an image.
            # Telegram "document" can be anything, but if it's an image, we might want to check it.
            # For now, let's assume we only check photos or if we can detect mime type.
            # The task says "file_type" is literal.
            # LLaVA works on images.
            if file_data and task.file_type == "photo":
                image_description = await call_ollama_llava(file_data)
                logger.info(f"Image description: {image_description}")

    # 2. Call Ollama Aya
    result = await call_ollama_aya(task.text_content, task.caption, image_description)

    async with async_session() as session:
        trigger = await session.get(Trigger, task.trigger_id)
        if not trigger:
            logger.warning(f"Trigger {task.trigger_id} not found")
            return

        if not result:
            # Error case
            trigger.moderation_status = ModerationStatus.FLAGGED
            trigger.moderation_reason = "AI Error"
            await session.commit()

            # Send alert
            alert = ModerationAlert(
                trigger_id=task.trigger_id, chat_id=task.chat_id, category="Error", reasoning="AI failed to process"
            )
            await broker.publish(alert, "q.moderation.alerts")
            return

        # 3. Update DB based on result
        if result.category == "Safe":
            trigger.moderation_status = ModerationStatus.SAFE
            trigger.moderation_reason = "Safe"
            await session.commit()
        else:
            trigger.moderation_status = ModerationStatus.FLAGGED
            trigger.moderation_reason = result.category
            await session.commit()

            # 4. Publish Alert
            alert = ModerationAlert(
                trigger_id=task.trigger_id,
                chat_id=task.chat_id,
                category=result.category,
                confidence=result.confidence,
                reasoning=result.reasoning,
            )
            await broker.publish(alert, "q.moderation.alerts")
            logger.info(f"Trigger {task.trigger_id} flagged as {result.category}")
