"""Root conftest — sets environment BEFORE any app imports."""

import os
import subprocess

# ── Test environment variables (MUST be set before any app module import) ──────
os.environ["POSTGRES_URL"] = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/trigger_test",
)
os.environ["VALKEY_URL"] = os.getenv("TEST_VALKEY_URL", "redis://localhost:6379/1")
os.environ["BOT_TOKEN"] = "0000000000:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
os.environ["WEBAPP_URL"] = "http://localhost:3000"
os.environ["WEBHOOK_URL"] = "http://localhost:8000/webhook"
os.environ["WEBHOOK_PATH"] = "/webhook"
os.environ["SECRET_TOKEN"] = "test-secret-token"
os.environ["S3_ACCESS_KEY"] = "minioadmin"
os.environ["S3_SECRET_KEY"] = "minioadmin"
os.environ["S3_ENDPOINT"] = "localhost:9000"
os.environ["MODERATION_CHANNEL_ID"] = "-1001234567890"
os.environ["RABBITMQ_URL"] = "amqp://guest:guest@localhost:5672/"
os.environ["SESSION_SECRET_KEY"] = "test-session-secret-key-at-least-32chars"

# ── Now safe to import app modules ────────────────────────────────────────────
from unittest.mock import AsyncMock, patch  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.models import Base  # noqa: E402  — registers all models with metadata

_ASYNC_URL = os.environ["POSTGRES_URL"]
if _ASYNC_URL.startswith("postgresql://"):
    _ASYNC_URL = _ASYNC_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
_SYNC_URL = _ASYNC_URL.replace("+asyncpg", "")


# ── Session-scoped: run Alembic migrations (matches production schema exactly) ─
@pytest.fixture(scope="session", autouse=True)
def _setup_database():
    """Run Alembic migrations to set up the test DB exactly like production."""
    # Reset schema for a clean start
    sync_engine = create_engine(_SYNC_URL, echo=False)
    with sync_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    sync_engine.dispose()

    # Run alembic upgrade head — uses POSTGRES_URL from env (our test DB)
    result = subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Alembic migration failed:\n{result.stderr}")

    yield

    # Teardown: drop everything
    sync_engine = create_engine(_SYNC_URL, echo=False)
    with sync_engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    sync_engine.dispose()


# ── Shared async engine (session-scoped, same loop as all tests) ──────────────
@pytest_asyncio.fixture(scope="session")
async def _async_engine():
    """Session-scoped async engine — all tests share the same event loop."""
    engine = create_async_engine(_ASYNC_URL, echo=False)
    yield engine
    await engine.dispose()


# ── Per-test async session ────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def db_session(_async_engine):
    """Provide an async session; tables are truncated after the test."""
    factory = async_sessionmaker(_async_engine, expire_on_commit=False)
    async with factory() as session:
        yield session

    # Cleanup using the SAME engine/loop
    async with _async_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


# ── Valkey (real instance) ────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def valkey_client():
    """Real Valkey/Redis client; flushes the test DB after each test."""
    from redis.asyncio import Redis

    client = Redis.from_url(os.environ["VALKEY_URL"], decode_responses=True)
    yield client
    await client.flushdb()
    await client.aclose()


# ── Mock: RabbitMQ broker ─────────────────────────────────────────────────────
@pytest.fixture
def mock_broker():
    with patch("app.core.broker.broker") as m:
        m.publish = AsyncMock()
        m.start = AsyncMock()
        m.stop = AsyncMock()
        yield m


# ── Mock: S3 storage ─────────────────────────────────────────────────────────
@pytest.fixture
def mock_storage():
    with patch("app.core.storage.storage") as m:
        m.put_file = AsyncMock()
        m.get_file = AsyncMock(return_value=None)
        m.delete_file = AsyncMock()
        m.exists = AsyncMock(return_value=False)
        m.ensure_bucket = AsyncMock()
        yield m


# ── Mock: Telegram bot ───────────────────────────────────────────────────────
@pytest.fixture
def mock_bot():
    with patch("app.bot.instance.bot") as m:
        m.send_message = AsyncMock()
        m.send_photo = AsyncMock()
        m.send_video = AsyncMock()
        m.send_sticker = AsyncMock()
        m.send_animation = AsyncMock()
        m.send_document = AsyncMock()
        m.send_voice = AsyncMock()
        m.send_audio = AsyncMock()
        m.leave_chat = AsyncMock()
        m.get_chat_member = AsyncMock()
        m.get_chat = AsyncMock()
        m.set_webhook = AsyncMock()
        m.delete_webhook = AsyncMock()
        m.delete_ephemeral_message = AsyncMock()
        m.edit_ephemeral_message_text = AsyncMock()
        m.edit_ephemeral_message_reply_markup = AsyncMock()
        yield m


# ── Mock: Valkey module-level singleton ──────────────────────────────────────
@pytest.fixture
def mock_valkey():
    """Patch the module-level valkey singleton used by services."""
    with patch("app.core.valkey.valkey") as m:
        m.get = AsyncMock(return_value=None)
        m.set = AsyncMock()
        m.delete = AsyncMock()
        m.exists = AsyncMock(return_value=0)
        m.expire = AsyncMock()
        m.hset = AsyncMock()
        m.hget = AsyncMock(return_value=None)
        m.hincrby = AsyncMock()
        m.publish = AsyncMock()
        m.flushdb = AsyncMock()
        yield m
