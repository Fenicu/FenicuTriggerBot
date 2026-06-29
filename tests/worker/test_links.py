"""Tests for app/worker/links.py."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.worker.links import extract_links, safe_fetch, _is_public_host, _extract_summary


class TestExtractLinks:
    def test_http_url(self) -> None:
        urls, tg = extract_links("see https://example.com/x now")
        assert "https://example.com/x" in urls
        assert tg == []

    def test_tg_at_handle(self) -> None:
        urls, tg = extract_links("join @shop_channel")
        assert tg == ["@shop_channel"]

    def test_tme_link_normalized_to_handle(self) -> None:
        urls, tg = extract_links("https://t.me/shop_channel")
        assert tg == ["@shop_channel"]
        assert urls == []  # t.me не идёт в http-фетч

    def test_dedup_and_limit_inputs(self) -> None:
        # Регекс _AT_RE требует минимум 3 символа — используем валидные handles
        urls, tg = extract_links("@abc @abc @def")
        assert tg == ["@abc", "@def"]


class TestIsPublicHost:
    @pytest.mark.parametrize("host", ["127.0.0.1", "10.0.0.5", "192.168.1.1",
                                      "169.254.1.1", "localhost", "::1"])
    async def test_private_blocked(self, host: str) -> None:
        assert await _is_public_host(host) is False

    async def test_public_allowed(self) -> None:
        with patch("app.worker.links._resolve_ips", new_callable=AsyncMock,
                   return_value=["93.184.216.34"]):
            assert await _is_public_host("example.com") is True


class TestExtractSummary:
    def test_pulls_title_and_og(self) -> None:
        html = ('<html><head><title>Shop</title>'
                '<meta property="og:description" content="best deals"></head>'
                '<body>hello</body></html>')
        s = _extract_summary(html)
        assert "Shop" in s
        assert "best deals" in s


class TestSafeFetch:
    async def test_blocks_private_ip(self) -> None:
        with patch("app.worker.links._is_public_host", new_callable=AsyncMock, return_value=False):
            assert await safe_fetch("http://10.0.0.1/") is None

    async def test_rejects_non_http_scheme(self) -> None:
        assert await safe_fetch("file:///etc/passwd") is None
        assert await safe_fetch("ftp://x/") is None

    async def test_returns_summary_on_success(self) -> None:
        resp = AsyncMock()
        resp.status = 200
        resp.headers = {"Content-Type": "text/html"}
        resp.content.iter_chunked = MagicMock(return_value=_aiter([b"<title>Hi</title>"]))
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)
        session = AsyncMock()
        session.get = MagicMock(return_value=resp)
        with patch("app.worker.links._is_public_host", new_callable=AsyncMock, return_value=True), \
             patch("app.worker.links.get_session", new_callable=AsyncMock, return_value=session):
            out = await safe_fetch("https://example.com")
        assert out is not None and "Hi" in out


async def _aiter(items):  # type: ignore[return]
    """Вспомогательный async-генератор для мока aiohttp content.iter_chunked."""
    for i in items:
        yield i
