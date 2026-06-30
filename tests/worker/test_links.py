"""Tests for app/worker/links.py."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.worker.links import build_link_context, extract_links, safe_fetch, _is_public_host, _extract_summary


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
                                      "169.254.1.1", "localhost", "::1",
                                      "100.64.0.1"])  # CGNAT — is_global=False
    async def test_private_blocked(self, host: str) -> None:
        assert await _is_public_host(host) is False

    async def test_public_allowed(self) -> None:
        with patch("app.worker.links._resolve_ips", new_callable=AsyncMock,
                   return_value=["93.184.216.34"]):
            assert await _is_public_host("example.com") is True

    async def test_is_public_host_oversized_label_fails_closed(self) -> None:
        """Метка >63 символа вызывает UnicodeEncodeError в getaddrinfo — должна вернуть False, не упасть."""
        oversized = "a" * 64 + ".com"
        result = await _is_public_host(oversized)
        assert result is False


class TestExtractSummary:
    def test_pulls_title_and_og(self) -> None:
        html = ('<html><head><title>Shop</title>'
                '<meta property="og:description" content="best deals"></head>'
                '<body>hello</body></html>')
        s = _extract_summary(html)
        assert "Shop" in s
        assert "best deals" in s


class TestSafeFetch:
    async def test_safe_fetch_malformed_url_returns_none(self) -> None:
        """Неправильный URL вроде http://[::1 должен вернуть None, не упасть."""
        result = await safe_fetch("http://[::1")
        assert result is None

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


    async def test_safe_fetch_follows_redirect_and_reports_chain(self) -> None:
        """302 → казино раскрывается: цепочка редиректа и заголовок финальной страницы в ответе."""
        resp1 = AsyncMock()
        resp1.status = 302
        resp1.headers = {"Location": "https://casino.example/registration?affb_id=9"}
        resp1.__aenter__ = AsyncMock(return_value=resp1)
        resp1.__aexit__ = AsyncMock(return_value=False)

        resp2 = AsyncMock()
        resp2.status = 200
        resp2.headers = {"Content-Type": "text/html"}
        resp2.content.iter_chunked = MagicMock(return_value=_aiter([b"<title>Casino</title>"]))
        resp2.__aenter__ = AsyncMock(return_value=resp2)
        resp2.__aexit__ = AsyncMock(return_value=False)

        session = AsyncMock()
        session.get = MagicMock(side_effect=[resp1, resp2])

        with patch("app.worker.links._is_public_host", new=AsyncMock(return_value=True)), \
             patch("app.worker.links.get_session", new_callable=AsyncMock, return_value=session):
            result = await safe_fetch("https://rwn-irrs10.com/cfc8ad80d")

        assert result is not None
        assert "casino.example" in result
        assert "Casino" in result

    async def test_safe_fetch_redirect_to_private_is_blocked(self) -> None:
        """Редирект на приватный хост: SSRF-проверка блокирует второй GET — контент не вытекает."""
        resp = AsyncMock()
        resp.status = 302
        resp.headers = {"Location": "http://10.0.0.1/"}
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)

        session = AsyncMock()
        session.get = MagicMock(return_value=resp)

        async def mock_is_public(host: str) -> bool:
            # 10.0.0.1 — приватный; всё остальное считаем публичным
            return host != "10.0.0.1"

        with patch("app.worker.links._is_public_host", new=mock_is_public), \
             patch("app.worker.links.get_session", new_callable=AsyncMock, return_value=session):
            result = await safe_fetch("https://example.com/page")

        # Только один GET выполнен — к example.com; к 10.0.0.1 запроса не было
        assert session.get.call_count == 1
        # Приватный хост не зафетчен и не попал в результат
        assert result is None

    async def test_safe_fetch_redirect_loop_stops(self) -> None:
        """Бесконечная цепочка редиректов останавливается на лимите без зависания."""
        from app.core.config import settings as _s

        max_calls = _s.LINK_FETCH_MAX_REDIRECTS + 1

        def make_redirect(n: int) -> AsyncMock:
            r = AsyncMock()
            r.status = 302
            r.headers = {"Location": f"https://hop{n}.example/"}
            r.__aenter__ = AsyncMock(return_value=r)
            r.__aexit__ = AsyncMock(return_value=False)
            return r

        responses = [make_redirect(i) for i in range(max_calls)]
        session = AsyncMock()
        session.get = MagicMock(side_effect=responses)

        with patch("app.worker.links._is_public_host", new=AsyncMock(return_value=True)), \
             patch("app.worker.links.get_session", new_callable=AsyncMock, return_value=session):
            result = await safe_fetch("https://start.example/")

        assert result is not None
        assert "hop" in result
        assert session.get.call_count <= max_calls


class TestBuildLinkContext:
    async def test_build_link_context_never_raises_on_bad_url(self) -> None:
        """build_link_context с невалидными URL не должен бросать исключение, возвращает строку."""
        oversized_host = "https://" + "a" * 64 + ".com"
        text = f"http://[::1 and {oversized_host}"
        # resolve_tg не нужен (нет TG-ссылок); сетевых вызовов не будет — оба URL дропнутся в safe_fetch
        result = await build_link_context(text, "")
        assert isinstance(result, str)


async def _aiter(items):  # type: ignore[return]
    """Вспомогательный async-генератор для мока aiohttp content.iter_chunked."""
    for i in items:
        yield i
