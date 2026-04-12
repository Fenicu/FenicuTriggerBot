"""Integration test fixtures — real DB, mocked external services."""

import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture(autouse=True)
def _mock_valkey_for_services():
    """Auto-mock the module-level valkey singleton so service code doesn't need real Redis.

    We patch both the canonical module AND all service modules that import valkey
    at module level (creating local bindings that won't see the canonical patch).
    """
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock()
    mock.delete = AsyncMock()
    mock.exists = AsyncMock(return_value=0)
    mock.expire = AsyncMock()
    mock.hset = AsyncMock()
    mock.hget = AsyncMock(return_value=None)
    mock.hincrby = AsyncMock()
    mock.publish = AsyncMock()
    with (
        patch("app.core.valkey.valkey", mock),
        patch("app.services.trigger_service.valkey", mock),
        patch("app.services.moderation_history_service.valkey", mock),
    ):
        yield mock


@pytest.fixture(autouse=True)
def _mock_broker_for_services():
    """Auto-mock the broker so publishing doesn't require RabbitMQ."""
    mock = AsyncMock()
    mock.publish = AsyncMock()
    with (
        patch("app.core.broker.broker", mock),
        patch("app.services.trigger_service.broker", mock),
    ):
        yield mock


@pytest.fixture(autouse=True)
def _mock_storage_for_services():
    """Auto-mock the S3 storage."""
    mock = AsyncMock()
    mock.put_file = AsyncMock()
    mock.get_file = AsyncMock(return_value=None)
    mock.delete_file = AsyncMock()
    mock.exists = AsyncMock(return_value=False)
    with (
        patch("app.core.storage.storage", mock),
        patch("app.services.trigger_service.storage", mock),
    ):
        yield mock
