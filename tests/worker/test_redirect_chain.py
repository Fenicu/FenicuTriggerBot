"""Tests for redirect-chain sanitization and its end-to-end propagation into ModerationAlert."""

from unittest.mock import AsyncMock, MagicMock, patch

from app.bot.handlers.moderation import sanitize_redirect_chain
from app.schemas.moderation import ModerationAlert
from app.worker.links import build_link_context


class TestSanitizeRedirectChain:
    def test_strips_query_and_fragment(self) -> None:
        """Query-параметры (там бывают трекинг-токены) и fragment отрезаются."""
        chain = ["https://short.link/abc", "https://casino.example/reg?ref=affid123&aff=9#promo"]
        result = sanitize_redirect_chain(chain)
        assert result == ["https://short.link/abc", "https://casino.example/reg"]

    def test_empty_chain_returns_empty(self) -> None:
        """Пустой список возвращается пустым."""
        assert sanitize_redirect_chain([]) == []

    def test_preserves_scheme_host_path_only(self) -> None:
        """Сохраняет только схему, хост и путь (query удаляется)."""
        chain = ["http://example.com:8080/path/to/page?x=1"]
        result = sanitize_redirect_chain(chain)
        assert result == ["http://example.com:8080/path/to/page"]

    def test_no_query_no_change(self) -> None:
        """URL без query/fragment остаётся как есть."""
        chain = ["https://example.com/plain/path"]
        assert sanitize_redirect_chain(chain) == chain


class TestRedirectChainEndToEnd:
    """safe_fetch (редирект) -> build_link_context -> ModerationAlert.redirect_chain заполнен."""

    async def test_chain_reaches_moderation_alert(self) -> None:
        """Цепочка редиректов проходит через build_link_context в ModerationAlert."""
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

        with (
            patch("app.worker.links._is_public_host", new=AsyncMock(return_value=True)),
            patch("app.worker.links.get_session", new_callable=AsyncMock, return_value=session),
        ):
            context_str, chains = await build_link_context("https://rwn-irrs10.com/cfc8ad80d", "")

        # Текст для LLM не изменился (по-прежнему содержит цепочку и заголовок финальной страницы)
        assert "casino.example" in context_str
        assert "Casino" in context_str

        assert len(chains) == 1
        redirect_chain = chains[0]
        assert redirect_chain == [
            "https://rwn-irrs10.com/cfc8ad80d",
            "https://casino.example/registration?affb_id=9",
        ]

        alert = ModerationAlert(
            trigger_id=1,
            chat_id=-100500,
            category="Scam",
            confidence=0.9,
            reasoning="test",
            redirect_chain=redirect_chain,
        )
        assert alert.redirect_chain == redirect_chain

    async def test_no_redirect_gives_no_chains(self) -> None:
        """Прямой 200 без редиректов — chains пуст, alert без redirect_chain."""
        resp = AsyncMock()
        resp.status = 200
        resp.headers = {"Content-Type": "text/html"}
        resp.content.iter_chunked = MagicMock(return_value=_aiter([b"<title>Hi</title>"]))
        resp.__aenter__ = AsyncMock(return_value=resp)
        resp.__aexit__ = AsyncMock(return_value=False)

        session = AsyncMock()
        session.get = MagicMock(return_value=resp)

        with (
            patch("app.worker.links._is_public_host", new=AsyncMock(return_value=True)),
            patch("app.worker.links.get_session", new_callable=AsyncMock, return_value=session),
        ):
            context_str, chains = await build_link_context("https://example.com", "")

        assert "Hi" in context_str
        assert chains == []

        alert = ModerationAlert(
            trigger_id=1,
            chat_id=-100500,
            category="Safe",
            redirect_chain=chains[0] if chains else None,
        )
        assert alert.redirect_chain is None


async def _aiter(items):  # type: ignore[return]
    """Вспомогательный async-генератор для мока aiohttp content.iter_chunked."""
    for i in items:
        yield i
