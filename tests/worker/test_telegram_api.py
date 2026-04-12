"""Tests for app/worker/telegram.py — Telegram file download helpers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.worker.telegram import (
    MAX_MEMORY_SIZE,
    download_file,
    download_file_to_path,
    get_telegram_file_url,
)


def _make_response(status=200, json_data=None, content_length=None, chunks=None):
    """Build a mock aiohttp response."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data or {})
    resp.content_length = content_length

    if chunks is not None:
        async def iter_chunked(size):
            for chunk in chunks:
                yield chunk

        resp.content = MagicMock()
        resp.content.iter_chunked = iter_chunked
    else:
        async def empty_iter(size):
            return
            yield  # Make it a generator

        resp.content = MagicMock()
        resp.content.iter_chunked = empty_iter

    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


# ── get_telegram_file_url ────────────────────────────────────────────────────


class TestGetTelegramFileUrl:
    async def test_returns_url_for_valid_file(self):
        json_data = {"ok": True, "result": {"file_path": "photos/file_123.jpg"}}
        resp = _make_response(status=200, json_data=json_data)
        session = AsyncMock()
        session.get = MagicMock(return_value=resp)

        with (
            patch("app.worker.telegram.get_session", new_callable=AsyncMock, return_value=session),
            patch("app.worker.telegram.settings") as mock_settings,
        ):
            mock_settings.BOT_TOKEN = "123:ABC"
            mock_settings.TELEGRAM_BOT_API_URL = ""

            result = await get_telegram_file_url("file_id_123")

        assert result == "https://api.telegram.org/file/bot123:ABC/photos/file_123.jpg"

    async def test_returns_none_on_http_error(self):
        resp = _make_response(status=404)
        session = AsyncMock()
        session.get = MagicMock(return_value=resp)

        with (
            patch("app.worker.telegram.get_session", new_callable=AsyncMock, return_value=session),
            patch("app.worker.telegram.settings") as mock_settings,
        ):
            mock_settings.BOT_TOKEN = "123:ABC"
            mock_settings.TELEGRAM_BOT_API_URL = ""

            result = await get_telegram_file_url("bad_file_id")

        assert result is None

    async def test_returns_none_when_api_not_ok(self):
        json_data = {"ok": False, "error_code": 400, "description": "Bad Request"}
        resp = _make_response(status=200, json_data=json_data)
        session = AsyncMock()
        session.get = MagicMock(return_value=resp)

        with (
            patch("app.worker.telegram.get_session", new_callable=AsyncMock, return_value=session),
            patch("app.worker.telegram.settings") as mock_settings,
        ):
            mock_settings.BOT_TOKEN = "123:ABC"
            mock_settings.TELEGRAM_BOT_API_URL = ""

            result = await get_telegram_file_url("bad_file_id")

        assert result is None

    async def test_uses_local_bot_api_url(self):
        json_data = {"ok": True, "result": {"file_path": "photos/file_123.jpg"}}
        resp = _make_response(status=200, json_data=json_data)
        session = AsyncMock()
        session.get = MagicMock(return_value=resp)

        with (
            patch("app.worker.telegram.get_session", new_callable=AsyncMock, return_value=session),
            patch("app.worker.telegram.settings") as mock_settings,
        ):
            mock_settings.BOT_TOKEN = "123:ABC"
            mock_settings.TELEGRAM_BOT_API_URL = "http://local-api:8081"

            result = await get_telegram_file_url("file_id_123")

        assert result == "http://local-api:8081/file/bot123:ABC/photos/file_123.jpg"

    async def test_strips_absolute_path_for_local_api(self):
        """Local Bot API may return absolute paths containing the token."""
        json_data = {"ok": True, "result": {"file_path": "/home/bot/123:ABC/photos/file.jpg"}}
        resp = _make_response(status=200, json_data=json_data)
        session = AsyncMock()
        session.get = MagicMock(return_value=resp)

        with (
            patch("app.worker.telegram.get_session", new_callable=AsyncMock, return_value=session),
            patch("app.worker.telegram.settings") as mock_settings,
        ):
            mock_settings.BOT_TOKEN = "123:ABC"
            mock_settings.TELEGRAM_BOT_API_URL = "http://local-api:8081"

            result = await get_telegram_file_url("file_id_123")

        assert result == "http://local-api:8081/file/bot123:ABC/photos/file.jpg"


# ── download_file ────────────────────────────────────────────────────────────


class TestDownloadFile:
    async def test_downloads_small_file(self):
        data = b"file contents here"
        resp = _make_response(status=200, content_length=len(data), chunks=[data])
        session = AsyncMock()
        session.get = MagicMock(return_value=resp)

        with patch("app.worker.telegram.get_session", new_callable=AsyncMock, return_value=session):
            result = await download_file("https://example.com/file.jpg")

        assert result == data

    async def test_returns_none_on_http_error(self):
        resp = _make_response(status=500)
        session = AsyncMock()
        session.get = MagicMock(return_value=resp)

        with patch("app.worker.telegram.get_session", new_callable=AsyncMock, return_value=session):
            result = await download_file("https://example.com/file.jpg")

        assert result is None

    async def test_returns_none_when_content_length_exceeds_limit(self):
        resp = _make_response(status=200, content_length=MAX_MEMORY_SIZE + 1)
        session = AsyncMock()
        session.get = MagicMock(return_value=resp)

        with patch("app.worker.telegram.get_session", new_callable=AsyncMock, return_value=session):
            result = await download_file("https://example.com/huge.bin")

        assert result is None

    async def test_returns_none_when_stream_exceeds_limit(self):
        """Even without Content-Length, streaming should abort on oversized data."""
        # Generate chunks that exceed limit
        chunk = b"x" * 65536
        num_chunks = (MAX_MEMORY_SIZE // 65536) + 2
        chunks = [chunk] * num_chunks

        resp = _make_response(status=200, content_length=None, chunks=chunks)
        session = AsyncMock()
        session.get = MagicMock(return_value=resp)

        with patch("app.worker.telegram.get_session", new_callable=AsyncMock, return_value=session):
            result = await download_file("https://example.com/huge_stream.bin")

        assert result is None

    async def test_custom_max_size(self):
        data = b"x" * 200
        resp = _make_response(status=200, content_length=200, chunks=[data])
        session = AsyncMock()
        session.get = MagicMock(return_value=resp)

        with patch("app.worker.telegram.get_session", new_callable=AsyncMock, return_value=session):
            # Should fail with a very small limit
            result = await download_file("https://example.com/file.jpg", max_size=100)

        assert result is None

    async def test_multiple_chunks(self):
        chunks = [b"chunk1", b"chunk2", b"chunk3"]
        resp = _make_response(status=200, content_length=18, chunks=chunks)
        session = AsyncMock()
        session.get = MagicMock(return_value=resp)

        with patch("app.worker.telegram.get_session", new_callable=AsyncMock, return_value=session):
            result = await download_file("https://example.com/file.jpg")

        assert result == b"chunk1chunk2chunk3"


# ── download_file_to_path ────────────────────────────────────────────────────


class TestDownloadFileToPath:
    async def test_downloads_to_disk(self, tmp_path):
        chunks = [b"hello ", b"world"]
        resp = _make_response(status=200, chunks=chunks)
        session = AsyncMock()
        session.get = MagicMock(return_value=resp)
        target = str(tmp_path / "output.bin")

        with patch("app.worker.telegram.get_session", new_callable=AsyncMock, return_value=session):
            result = await download_file_to_path("https://example.com/file.mp4", target)

        assert result is True
        with open(target, "rb") as f:
            assert f.read() == b"hello world"

    async def test_returns_false_on_http_error(self, tmp_path):
        resp = _make_response(status=403)
        session = AsyncMock()
        session.get = MagicMock(return_value=resp)
        target = str(tmp_path / "output.bin")

        with patch("app.worker.telegram.get_session", new_callable=AsyncMock, return_value=session):
            result = await download_file_to_path("https://example.com/file.mp4", target)

        assert result is False
