from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_current_admin_from_query, validate_init_data_from_query
from app.core.database import get_db
from app.api.v1.endpoints import triggers


@pytest.mark.parametrize("exists,status", [(True, 200), (False, 404)])
async def test_sse_closes_session_before_streaming(exists, status):
    app = FastAPI()
    app.include_router(triggers.router, prefix="/triggers")
    app.dependency_overrides[validate_init_data_from_query] = lambda: {"type": "token", "user_id": 1}
    closed = False
    session = AsyncMock()
    session.get.return_value = object() if exists else None

    @asynccontextmanager
    async def factory():
        nonlocal closed
        try:
            yield session
        finally:
            closed = True

    async def database():
        async with factory() as active_session:
            yield active_session

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_admin_from_query] = lambda: object()

    async def events(trigger_id):
        assert closed, "Database session is still open while streaming"
        yield "data: ready\n\n"

    async def authorize(auth_info, session):
        return object()

    with (
        patch.object(triggers, "async_session_factory", factory, create=True),
        patch.object(triggers, "_get_admin_from_auth_info", authorize, create=True),
        patch.object(triggers, "moderation_history_stream", events),
    ):
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            response = await client.get("/triggers/1/moderation-history/stream")
    assert response.status_code == status
    assert closed
