"""API test fixtures — httpx client, dependency overrides."""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
def _mock_externals():
    """Auto-mock broker, storage, valkey, bot for API tests."""
    with (
        patch("app.core.valkey.valkey") as mock_v,
        patch("app.services.trigger_service.valkey") as mock_sv,
        patch("app.services.moderation_history_service.valkey") as mock_mhv,
        patch("app.api.v1.endpoints.captcha.valkey") as mock_captcha_valkey,
        patch("app.core.broker.broker") as mock_b,
        patch("app.services.trigger_service.broker") as mock_sb,
        patch("app.core.storage.storage") as mock_s,
        patch("app.services.trigger_service.storage") as mock_ss,
        patch("app.bot.instance.bot") as mock_bot,
        patch("app.api.v1.endpoints.chats.bot") as mock_chats_bot,
        patch("app.api.v1.endpoints.captcha.bot") as mock_captcha_bot,
    ):
        # Propagate mock config to service-level bindings
        for m in (mock_v, mock_sv, mock_mhv, mock_captcha_valkey):
            m.get = AsyncMock(return_value=None)
            m.set = AsyncMock()
            m.delete = AsyncMock()
            m.exists = AsyncMock(return_value=0)
            m.publish = AsyncMock()
        for m in (mock_b, mock_sb):
            m.publish = AsyncMock()
        for m in (mock_s, mock_ss):
            m.delete_file = AsyncMock()
        mock_s.get_file = AsyncMock(return_value=None)
        mock_s.put_file = AsyncMock()
        mock_s.exists = AsyncMock(return_value=False)
        mock_s.ensure_bucket = AsyncMock()
        mock_bot.send_message = AsyncMock()
        mock_chats_bot.send_message = AsyncMock()
        mock_chats_bot.leave_chat = AsyncMock()
        mock_captcha_bot.restrict_chat_member = AsyncMock()
        mock_captcha_bot.edit_message_reply_markup = AsyncMock()
        mock_captcha_bot.edit_message_text = AsyncMock()
        mock_captcha_bot.edit_ephemeral_message_reply_markup = AsyncMock()
        mock_captcha_bot.edit_ephemeral_message_text = AsyncMock()
        yield


@pytest_asyncio.fixture
async def api_client(db_session: AsyncSession):
    """Provide an httpx AsyncClient wired to the FastAPI app with DB override."""
    from app.api.v1.router import api_router
    from app.core.database import get_db
    from fastapi import FastAPI

    test_app = FastAPI()
    test_app.include_router(api_router, prefix="/api/v1")

    async def _override_db():
        yield db_session

    test_app.dependency_overrides[get_db] = _override_db

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as client:
        yield client
