import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse

from aiogram.types import Update
from fastapi import FastAPI, Request

from app.core.logging import setup_logging

setup_logging()

from app.bot.dispatcher import bot, dp
from app.core.config import settings
from app.core.database import engine
from app.core.valkey import valkey

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Управление жизненным циклом приложения."""
    logger.info("Starting application lifespan")

    await valkey.ping()

    logger.info(f"Setting webhook to {settings.WEBHOOK_PATH}")
    try:
        await bot.set_webhook(
            url=settings.WEBHOOK_PATH,
            secret_token=settings.SECRET_TOKEN,
            drop_pending_updates=True,
            allowed_updates=dp.resolve_used_update_types(),
        )
        logger.info("Webhook set successfully")
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")

    yield

    logger.info("Shutting down application")
    await bot.delete_webhook()
    await valkey.aclose()
    await engine.dispose()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)


webhook_path = settings.WEBHOOK_PATH
if webhook_path.startswith("http"):
    parsed = urlparse(webhook_path)
    webhook_path = parsed.path


@app.post(webhook_path)
async def bot_webhook(request: Request) -> dict[str, Any]:
    """Обработчик вебхука от Telegram."""
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_token != settings.SECRET_TOKEN:
        return {"status": "unauthorized"}

    update_data = await request.json()
    update = Update.model_validate(update_data)
    await dp.feed_webhook_update(bot, update)
    return {"status": "ok"}


@app.get(webhook_path)
async def health(request: Request) -> dict[str, Any]:
    """Обработчик вебхука."""
    return {"status": "ok"}
