"""Tests for /api/v1/media/ endpoints."""

import gzip
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.auth import create_auth_token
from app.api.v1.endpoints.media import generate_media_token
from tests.factories import create_user

# Эндпоинты /media/info и /media/proxy требуют ЛИБО валидного админа/модератора
# (initData/Bearer через Depends(get_current_admin)), ЛИБО подписанного
# короткоживущего токена в query, привязанного к конкретному file_id.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _admin_headers(user_id: int) -> dict[str, str]:
    token = create_auth_token(user_id)
    return {"Authorization": f"Bearer {token}"}


async def _seed_admin(session: AsyncSession, *, moderator: bool = True) -> int:
    user = await create_user(session, is_bot_moderator=moderator)
    await session.commit()
    return user.id


# ---------------------------------------------------------------------------
# GET /media/info
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_media_info_no_auth_no_token_401(api_client: AsyncClient):
    resp = await api_client.get("/api/v1/media/info", params={"file_id": "abc123"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_media_info_success_with_admin_auth(api_client: AsyncClient, db_session: AsyncSession):
    admin_id = await _seed_admin(db_session)
    mock_file = MagicMock()
    mock_file.file_size = 12345
    mock_file.file_path = "photos/file_0.jpg"

    with patch("app.api.v1.endpoints.media.bot") as mock_bot:
        mock_bot.get_file = AsyncMock(return_value=mock_file)
        resp = await api_client.get(
            "/api/v1/media/info",
            params={"file_id": "abc123"},
            headers=_admin_headers(admin_id),
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["file_size"] == 12345
    assert body["file_path"] == "photos/file_0.jpg"


@pytest.mark.asyncio
async def test_media_info_success_with_valid_token(api_client: AsyncClient):
    """Без авторизации, но с валидным подписанным токеном — доступ разрешён."""
    mock_file = MagicMock()
    mock_file.file_size = 999
    mock_file.file_path = "photos/file_9.jpg"
    token = generate_media_token("abc123")

    with patch("app.api.v1.endpoints.media.bot") as mock_bot:
        mock_bot.get_file = AsyncMock(return_value=mock_file)
        resp = await api_client.get(
            "/api/v1/media/info",
            params={"file_id": "abc123", "token": token},
        )

    assert resp.status_code == 200
    assert resp.json()["file_size"] == 999


@pytest.mark.asyncio
async def test_media_info_expired_token_401(api_client: AsyncClient):
    expired_token = generate_media_token("abc123", ttl_seconds=-1)
    resp = await api_client.get(
        "/api/v1/media/info",
        params={"file_id": "abc123", "token": expired_token},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_media_info_tampered_token_401(api_client: AsyncClient):
    token = generate_media_token("abc123")
    encoded, _sig = token.rsplit(".", 1)
    tampered = f"{encoded}.deadbeef"
    resp = await api_client.get(
        "/api/v1/media/info",
        params={"file_id": "abc123", "token": tampered},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_media_info_token_for_other_file_id_401(api_client: AsyncClient):
    """Токен, выписанный для одного file_id, не должен работать для другого."""
    token = generate_media_token("other_file")
    resp = await api_client.get(
        "/api/v1/media/info",
        params={"file_id": "abc123", "token": token},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_media_info_non_admin_403(api_client: AsyncClient, db_session: AsyncSession):
    user_id = await _seed_admin(db_session, moderator=False)
    resp = await api_client.get(
        "/api/v1/media/info",
        params={"file_id": "abc123"},
        headers=_admin_headers(user_id),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_media_info_missing_file_id_422(api_client: AsyncClient):
    resp = await api_client.get("/api/v1/media/info")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_media_info_telegram_error_returns_generic_message(api_client: AsyncClient, db_session: AsyncSession):
    """Технический текст ошибки aiogram не должен утекать в detail."""
    admin_id = await _seed_admin(db_session)
    with patch("app.api.v1.endpoints.media.bot") as mock_bot:
        mock_bot.get_file = AsyncMock(side_effect=Exception("Bad file_id: secret internal detail"))
        resp = await api_client.get(
            "/api/v1/media/info",
            params={"file_id": "bad_id"},
            headers=_admin_headers(admin_id),
        )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "secret internal detail" not in detail
    assert "Bad file_id" not in detail


# ---------------------------------------------------------------------------
# GET /media/token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_media_token_requires_admin_401(api_client: AsyncClient):
    resp = await api_client.get("/api/v1/media/token", params={"file_id": "abc123"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_media_token_non_admin_403(api_client: AsyncClient, db_session: AsyncSession):
    user_id = await _seed_admin(db_session, moderator=False)
    resp = await api_client.get(
        "/api/v1/media/token",
        params={"file_id": "abc123"},
        headers=_admin_headers(user_id),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_media_token_success_and_usable(api_client: AsyncClient, db_session: AsyncSession):
    """Токен, выданный /media/token, должен открывать доступ к /media/proxy без Authorization."""
    admin_id = await _seed_admin(db_session)
    resp = await api_client.get(
        "/api/v1/media/token",
        params={"file_id": "cached_file"},
        headers=_admin_headers(admin_id),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["expires_in"] == 3600
    token = body["token"]

    cached_data = b"\xff\xd8\xffsome-jpeg-data"
    with patch("app.api.v1.endpoints.media.storage") as mock_storage:
        mock_storage.get_file = AsyncMock(return_value=(cached_data, "image/jpeg"))
        proxy_resp = await api_client.get(
            "/api/v1/media/proxy",
            params={"file_id": "cached_file", "token": token},
        )

    assert proxy_resp.status_code == 200
    assert proxy_resp.content == cached_data


# ---------------------------------------------------------------------------
# GET /media/proxy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_proxy_media_no_auth_no_token_401(api_client: AsyncClient):
    resp = await api_client.get("/api/v1/media/proxy", params={"file_id": "cached_file"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_proxy_media_cached(api_client: AsyncClient, db_session: AsyncSession):
    """When storage has the file cached, return it directly."""
    admin_id = await _seed_admin(db_session)
    cached_data = b"\xff\xd8\xffsome-jpeg-data"
    with patch("app.api.v1.endpoints.media.storage") as mock_storage:
        mock_storage.get_file = AsyncMock(return_value=(cached_data, "image/jpeg"))
        resp = await api_client.get(
            "/api/v1/media/proxy",
            params={"file_id": "cached_file"},
            headers=_admin_headers(admin_id),
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content == cached_data


@pytest.mark.asyncio
async def test_proxy_media_cached_with_valid_token(api_client: AsyncClient):
    cached_data = b"\xff\xd8\xffsome-jpeg-data"
    token = generate_media_token("cached_file")
    with patch("app.api.v1.endpoints.media.storage") as mock_storage:
        mock_storage.get_file = AsyncMock(return_value=(cached_data, "image/jpeg"))
        resp = await api_client.get(
            "/api/v1/media/proxy",
            params={"file_id": "cached_file", "token": token},
        )

    assert resp.status_code == 200
    assert resp.content == cached_data


@pytest.mark.asyncio
async def test_proxy_media_expired_token_401(api_client: AsyncClient):
    expired_token = generate_media_token("cached_file", ttl_seconds=-1)
    resp = await api_client.get(
        "/api/v1/media/proxy",
        params={"file_id": "cached_file", "token": expired_token},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_proxy_media_tampered_token_401(api_client: AsyncClient):
    token = generate_media_token("cached_file")
    encoded, _sig = token.rsplit(".", 1)
    tampered = f"{encoded}.deadbeef"
    resp = await api_client.get(
        "/api/v1/media/proxy",
        params={"file_id": "cached_file", "token": tampered},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_proxy_media_missing_file_id_422(api_client: AsyncClient):
    resp = await api_client.get("/api/v1/media/proxy")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_proxy_media_telegram_error_returns_generic_message(api_client: AsyncClient, db_session: AsyncSession):
    """When storage has no cache and Telegram get_file fails, return 400 with a neutral message."""
    admin_id = await _seed_admin(db_session)
    with (
        patch("app.api.v1.endpoints.media.storage") as mock_storage,
        patch("app.api.v1.endpoints.media.bot") as mock_bot,
    ):
        mock_storage.get_file = AsyncMock(return_value=None)
        mock_bot.get_file = AsyncMock(side_effect=Exception("Telegram error: token leaked here"))
        resp = await api_client.get(
            "/api/v1/media/proxy",
            params={"file_id": "bad_file"},
            headers=_admin_headers(admin_id),
        )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "token leaked here" not in detail


@pytest.mark.asyncio
async def test_proxy_media_regular_file(api_client: AsyncClient, db_session: AsyncSession):
    """Download a regular (non-TGS) file, cache it, and return."""
    admin_id = await _seed_admin(db_session)
    file_content = b"PNG-image-data-here"
    mock_file = MagicMock()
    mock_file.file_path = "photos/file_1.png"

    mock_api = MagicMock()
    mock_api.file_url.return_value = "https://api.telegram.org/file/bot123/photos/file_1.png"

    mock_session = MagicMock()
    mock_session.api = mock_api

    # Build an async context manager mock for aiohttp
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read = AsyncMock(return_value=file_content)

    with (
        patch("app.api.v1.endpoints.media.storage") as mock_storage,
        patch("app.api.v1.endpoints.media.bot") as mock_bot,
        patch("app.api.v1.endpoints.media.aiohttp.ClientSession") as mock_aiohttp,
    ):
        mock_storage.get_file = AsyncMock(return_value=None)
        mock_storage.put_file = AsyncMock()
        mock_bot.get_file = AsyncMock(return_value=mock_file)
        mock_bot.session = mock_session
        mock_bot.token = "123:abc"

        # Setup aiohttp mock chain
        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock(get=MagicMock(return_value=mock_ctx)))
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_aiohttp.return_value = mock_session_ctx

        resp = await api_client.get(
            "/api/v1/media/proxy",
            params={"file_id": "file_1"},
            headers=_admin_headers(admin_id),
        )

    assert resp.status_code == 200
    assert resp.content == file_content
    mock_storage.put_file.assert_awaited_once()


@pytest.mark.asyncio
async def test_proxy_media_tgs_file(api_client: AsyncClient, db_session: AsyncSession):
    """TGS (Lottie sticker) files are gzip-decompressed and returned as JSON."""
    admin_id = await _seed_admin(db_session)
    original_json = b'{"v":"5.5","fr":60}'
    compressed = gzip.compress(original_json)

    mock_file = MagicMock()
    mock_file.file_path = "stickers/file_2.tgs"

    mock_api = MagicMock()
    mock_api.file_url.return_value = "https://api.telegram.org/file/bot123/stickers/file_2.tgs"

    mock_session = MagicMock()
    mock_session.api = mock_api

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.read = AsyncMock(return_value=compressed)

    with (
        patch("app.api.v1.endpoints.media.storage") as mock_storage,
        patch("app.api.v1.endpoints.media.bot") as mock_bot,
        patch("app.api.v1.endpoints.media.aiohttp.ClientSession") as mock_aiohttp,
    ):
        mock_storage.get_file = AsyncMock(return_value=None)
        mock_storage.put_file = AsyncMock()
        mock_bot.get_file = AsyncMock(return_value=mock_file)
        mock_bot.session = mock_session
        mock_bot.token = "123:abc"

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=MagicMock(get=MagicMock(return_value=mock_ctx)))
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_aiohttp.return_value = mock_session_ctx

        resp = await api_client.get(
            "/api/v1/media/proxy",
            params={"file_id": "file_2"},
            headers=_admin_headers(admin_id),
        )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    assert resp.content == original_json
    mock_storage.put_file.assert_awaited_once_with("file_2", original_json, content_type="application/json")


# ---------------------------------------------------------------------------
# Unit tests for token helpers
# ---------------------------------------------------------------------------


def test_generate_media_token_roundtrip():
    """Юнит-проверка: валидный токен проходит верификацию для того же file_id."""
    from app.api.v1.endpoints.media import verify_media_token

    token = generate_media_token("some_file")
    assert verify_media_token("some_file", token) is True


def test_verify_media_token_rejects_malformed():
    from app.api.v1.endpoints.media import verify_media_token

    assert verify_media_token("some_file", "not-a-token") is False
