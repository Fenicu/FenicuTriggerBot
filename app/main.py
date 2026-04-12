import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from aiogram.types import Update
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1.router import api_router
from app.core.logging import setup_logging

setup_logging()

# Optional Sentry/GlitchTip integration
from app.core.config import settings as _settings

if _settings.SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=_settings.SENTRY_DSN,
        traces_sample_rate=0.1,
        release=_settings.BOT_VERSION,
        environment="production" if _settings.BOT_VERSION != "unknown" else "development",
    )

from app.bot.dispatcher import dp
from app.bot.instance import bot
from app.core.broker import broker
from app.core.config import settings
from app.core.database import engine
from app.core.storage import storage
from app.core.valkey import valkey

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Управление жизненным циклом приложения."""
    logger.info("Starting application lifespan")

    await valkey.ping()
    await storage.ensure_bucket()
    await broker.start()

    logger.info(f"Setting webhook to {settings.WEBHOOK_URL}")
    try:
        await bot.set_webhook(
            url=settings.WEBHOOK_URL,
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
    await broker.stop()
    await valkey.aclose()
    await engine.dispose()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SESSION_SECRET_KEY,
    https_only=True,
    same_site="lax",
)


app.include_router(api_router, prefix=f"{settings.URL_PREFIX}{settings.API_V1_STR}")

app.mount(f"{settings.URL_PREFIX}/webapp", StaticFiles(directory="frontend/dist", html=True), name="webapp")


@app.post(f"{settings.URL_PREFIX}{settings.WEBHOOK_PATH}")
async def bot_webhook(request: Request) -> dict[str, Any]:
    """Обработчик вебхука от Telegram."""
    secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret_token != settings.SECRET_TOKEN:
        return {"status": "unauthorized"}

    update_data = await request.json()
    update = Update.model_validate(update_data)
    await dp.feed_webhook_update(bot, update)
    return {"status": "ok"}


@app.get(f"{settings.URL_PREFIX}{settings.WEBHOOK_PATH}")
async def health(request: Request) -> dict[str, Any]:
    """Обработчик вебхука."""
    return {"status": "ok"}
