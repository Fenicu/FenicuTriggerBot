"""Tests for /api/v1/system/ endpoints."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# GET /system/config
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_system_config_returns_oidc_status(api_client: AsyncClient):
    """Config endpoint should return telegram_oidc_enabled field."""
    resp = await api_client.get("/api/v1/system/config")
    assert resp.status_code == 200
    body = resp.json()
    assert "telegram_oidc_enabled" in body
    assert isinstance(body["telegram_oidc_enabled"], bool)


@pytest.mark.asyncio
async def test_system_config_oidc_disabled_by_default(api_client: AsyncClient):
    """When TELEGRAM_OIDC_CLIENT_ID is empty, oidc should be disabled."""
    resp = await api_client.get("/api/v1/system/config")
    assert resp.status_code == 200
    # In test env, TELEGRAM_OIDC_CLIENT_ID is not set, so it should be empty/False
    assert resp.json()["telegram_oidc_enabled"] is False


@pytest.mark.asyncio
async def test_system_config_oidc_enabled():
    """When TELEGRAM_OIDC_CLIENT_ID is set, oidc should be enabled."""
    with patch("app.api.v1.endpoints.system.settings") as mock_settings:
        mock_settings.TELEGRAM_OIDC_CLIENT_ID = "some-client-id"

        from app.api.v1.endpoints.system import get_config

        result = await get_config()
        assert result["telegram_oidc_enabled"] is True


@pytest.mark.asyncio
async def test_system_config_no_auth_required(api_client: AsyncClient):
    """System config endpoint should be accessible without authentication."""
    resp = await api_client.get("/api/v1/system/config")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_system_config_response_shape(api_client: AsyncClient):
    """Response should contain exactly the expected keys."""
    resp = await api_client.get("/api/v1/system/config")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"telegram_oidc_enabled"}


@pytest.mark.asyncio
async def test_system_config_get_only(api_client: AsyncClient):
    """POST to the config endpoint should return 405."""
    resp = await api_client.post("/api/v1/system/config")
    assert resp.status_code == 405


@pytest.mark.asyncio
async def test_system_config_put_not_allowed(api_client: AsyncClient):
    """PUT to the config endpoint should return 405."""
    resp = await api_client.put("/api/v1/system/config", json={})
    assert resp.status_code == 405


@pytest.mark.asyncio
async def test_system_config_delete_not_allowed(api_client: AsyncClient):
    """DELETE to the config endpoint should return 405."""
    resp = await api_client.delete("/api/v1/system/config")
    assert resp.status_code == 405
