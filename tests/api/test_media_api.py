"""Tests for /api/v1/media/ endpoints."""

import gzip
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

# The media endpoints do NOT require authentication — they are open.
# See media.py: no Depends(get_current_admin) or Depends(get_authenticated_user).


# ---------------------------------------------------------------------------
# GET /media/info
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_media_info_success(api_client: AsyncClient):
    mock_file = MagicMock()
    mock_file.file_size = 12345
    mock_file.file_path = "photos/file_0.jpg"

    with patch("app.api.v1.endpoints.media.bot") as mock_bot:
        mock_bot.get_file = AsyncMock(return_value=mock_file)
        resp = await api_client.get("/api/v1/media/info", params={"file_id": "abc123"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["file_size"] == 12345
    assert body["file_path"] == "photos/file_0.jpg"


@pytest.mark.asyncio
async def test_media_info_missing_file_id_422(api_client: AsyncClient):
    resp = await api_client.get("/api/v1/media/info")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_media_info_telegram_error(api_client: AsyncClient):
    with patch("app.api.v1.endpoints.media.bot") as mock_bot:
        mock_bot.get_file = AsyncMock(side_effect=Exception("Bad file_id"))
        resp = await api_client.get("/api/v1/media/info", params={"file_id": "bad_id"})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /media/proxy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_proxy_media_cached(api_client: AsyncClient):
    """When storage has the file cached, return it directly."""
    cached_data = b"\xff\xd8\xffsome-jpeg-data"
    with patch("app.api.v1.endpoints.media.storage") as mock_storage:
        mock_storage.get_file = AsyncMock(return_value=(cached_data, "image/jpeg"))
        resp = await api_client.get("/api/v1/media/proxy", params={"file_id": "cached_file"})

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.content == cached_data


@pytest.mark.asyncio
async def test_proxy_media_missing_file_id_422(api_client: AsyncClient):
    resp = await api_client.get("/api/v1/media/proxy")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_proxy_media_telegram_error(api_client: AsyncClient):
    """When storage has no cache and Telegram get_file fails, return 400."""
    with (
        patch("app.api.v1.endpoints.media.storage") as mock_storage,
        patch("app.api.v1.endpoints.media.bot") as mock_bot,
    ):
        mock_storage.get_file = AsyncMock(return_value=None)
        mock_bot.get_file = AsyncMock(side_effect=Exception("Telegram error"))
        resp = await api_client.get("/api/v1/media/proxy", params={"file_id": "bad_file"})

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_proxy_media_regular_file(api_client: AsyncClient):
    """Download a regular (non-TGS) file, cache it, and return."""
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

        resp = await api_client.get("/api/v1/media/proxy", params={"file_id": "file_1"})

    assert resp.status_code == 200
    assert resp.content == file_content
    mock_storage.put_file.assert_awaited_once()


@pytest.mark.asyncio
async def test_proxy_media_tgs_file(api_client: AsyncClient):
    """TGS (Lottie sticker) files are gzip-decompressed and returned as JSON."""
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

        resp = await api_client.get("/api/v1/media/proxy", params={"file_id": "file_2"})

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    assert resp.content == original_json
    mock_storage.put_file.assert_awaited_once_with("file_2", original_json, content_type="application/json")
