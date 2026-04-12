"""Worker test fixtures."""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture(autouse=True)
def _mock_externals():
    mock_v = AsyncMock()
    mock_v.get = AsyncMock(return_value=None)
    mock_v.set = AsyncMock()
    mock_v.delete = AsyncMock()
    mock_v.exists = AsyncMock(return_value=0)
    mock_v.hset = AsyncMock()
    mock_v.hincrby = AsyncMock()
    mock_v.expire = AsyncMock()
    mock_v.publish = AsyncMock()

    mock_b = AsyncMock()
    mock_b.publish = AsyncMock()

    mock_s = AsyncMock()
    mock_s.delete_file = AsyncMock()

    with (
        patch("app.core.valkey.valkey", mock_v),
        patch("app.worker.service.valkey", mock_v),
        patch("app.services.moderation_history_service.valkey", mock_v),
        patch("app.core.broker.broker", mock_b),
        patch("app.worker.service.broker", mock_b),
        patch("app.core.storage.storage", mock_s),
        patch("app.services.trigger_service.valkey", mock_v),
        patch("app.services.trigger_service.broker", mock_b),
        patch("app.services.trigger_service.storage", mock_s),
    ):
        yield
