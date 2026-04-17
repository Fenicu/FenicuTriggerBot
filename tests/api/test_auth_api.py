"""Tests for /api/v1/auth/ endpoints and auth token functions."""

import secrets
import time
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.api.v1.endpoints.auth import (
    _pending_codes,
    create_auth_token,
    verify_auth_token,
)


# ---------------------------------------------------------------------------
# Unit: create_auth_token / verify_auth_token
# ---------------------------------------------------------------------------


def test_create_and_verify_token():
    user_id = 123456
    token = create_auth_token(user_id)
    assert verify_auth_token(token) == user_id


def test_verify_token_expired():
    user_id = 123456
    token = create_auth_token(user_id, ttl_seconds=-1)
    assert verify_auth_token(token) is None


def test_verify_token_bad_signature():
    user_id = 123456
    token = create_auth_token(user_id)
    # Corrupt the signature
    parts = token.split(".")
    parts[1] = "0" * len(parts[1])
    tampered = ".".join(parts)
    assert verify_auth_token(tampered) is None


def test_verify_token_invalid_format():
    assert verify_auth_token("not-a-valid-token") is None
    assert verify_auth_token("") is None
    assert verify_auth_token("a.b.c") is None


def test_verify_token_garbage_payload():
    """Token with valid structure but non-JSON payload."""
    import base64
    import hashlib
    import hmac

    from app.core.config import settings

    encoded = base64.urlsafe_b64encode(b"not-json").decode().rstrip("=")
    signature = hmac.new(settings.BOT_TOKEN.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    token = f"{encoded}.{signature}"
    assert verify_auth_token(token) is None


# ---------------------------------------------------------------------------
# POST /auth/oidc/exchange
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oidc_exchange_success(api_client: AsyncClient):
    code = secrets.token_urlsafe(32)
    _pending_codes[code] = {
        "token": "fake-auth-token",
        "name": "Test User",
        "expires": time.time() + 60,
    }

    resp = await api_client.post("/api/v1/auth/oidc/exchange", json={"code": code})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"] == "fake-auth-token"
    assert body["name"] == "Test User"
    # Code should be consumed (one-time use)
    assert code not in _pending_codes


@pytest.mark.asyncio
async def test_oidc_exchange_invalid_code(api_client: AsyncClient):
    resp = await api_client.post("/api/v1/auth/oidc/exchange", json={"code": "nonexistent-code"})
    assert resp.status_code == 403
    assert "invalid or expired" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_oidc_exchange_expired_code(api_client: AsyncClient):
    code = secrets.token_urlsafe(32)
    _pending_codes[code] = {
        "token": "expired-token",
        "name": "Expired User",
        "expires": time.time() - 10,  # already expired
    }

    resp = await api_client.post("/api/v1/auth/oidc/exchange", json={"code": code})
    assert resp.status_code == 403
    # The expired code should be cleaned up
    assert code not in _pending_codes


@pytest.mark.asyncio
async def test_oidc_exchange_missing_code_422(api_client: AsyncClient):
    resp = await api_client.post("/api/v1/auth/oidc/exchange", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_oidc_exchange_code_used_twice(api_client: AsyncClient):
    """Code is one-time use — second attempt must fail."""
    code = secrets.token_urlsafe(32)
    _pending_codes[code] = {
        "token": "one-time-token",
        "name": "User",
        "expires": time.time() + 60,
    }

    resp1 = await api_client.post("/api/v1/auth/oidc/exchange", json={"code": code})
    assert resp1.status_code == 200

    resp2 = await api_client.post("/api/v1/auth/oidc/exchange", json={"code": code})
    assert resp2.status_code == 403


# ---------------------------------------------------------------------------
# GET /auth/telegram-oidc/login (requires OIDC to be configured)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_telegram_oidc_login_not_configured(api_client: AsyncClient):
    """When TELEGRAM_OIDC_CLIENT_ID is empty, login should return 503."""
    resp = await api_client.get("/api/v1/auth/telegram-oidc/login", follow_redirects=False)
    assert resp.status_code == 503
    assert "не настроен" in resp.json()["detail"]
