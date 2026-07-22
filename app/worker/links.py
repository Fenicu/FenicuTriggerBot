"""Анализ ссылок в контенте триггера: извлечение, SSRF-safe фетч, резолв TG-сущностей."""

import asyncio
import contextlib
import ipaddress
import logging
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import aiohttp
from app.core.config import settings
from app.worker.http import get_session

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TME_RE = re.compile(r"(?:https?://)?t\.me/(\w{3,})", re.IGNORECASE)
_AT_RE = re.compile(r"(?<!\w)@(\w{3,})")


def extract_links(text: str) -> tuple[list[str], list[str]]:
    """Вернуть (http_urls, tg_handles). t.me и @name → нормализованные @handle."""
    if not text:
        return [], []
    text_wo_tme = _TME_RE.sub("", text)
    tg_raw = ["@" + m.group(1) for m in _TME_RE.finditer(text)] + [
        "@" + m.group(1) for m in _AT_RE.finditer(text_wo_tme)
    ]
    urls_raw = [u for u in _URL_RE.findall(text_wo_tme) if not u.lower().startswith(("https://t.me", "http://t.me"))]
    # dedup, сохранить порядок
    return list(dict.fromkeys(urls_raw)), list(dict.fromkeys(tg_raw))


class _SummaryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.description = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        elif tag == "meta":
            d = dict(attrs)
            key = (d.get("property") or d.get("name") or "").lower()
            if key in ("og:description", "description", "og:title") and d.get("content"):
                if "title" in key and not self.title:
                    self.title = d["content"]  # type: ignore[assignment]
                elif not self.description:
                    self.description = d["content"]  # type: ignore[assignment]

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and not self.title:
            self.title = data.strip()


def _extract_summary(html: str) -> str:
    p = _SummaryParser()
    with contextlib.suppress(Exception):
        p.feed(html)
    parts = [x for x in (p.title.strip(), p.description.strip()) if x]
    return " — ".join(parts)[:500]


async def _resolve_ips(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, None)
    return [i[4][0] for i in infos]


async def _is_public_host(host: str) -> bool:
    """False, если host резолвится в приватный/loopback/link-local/reserved/CGNAT IP (анти-SSRF)."""
    if host.lower() == "localhost":
        return False
    try:
        ips = await asyncio.wait_for(_resolve_ips(host), timeout=settings.LINK_FETCH_TIMEOUT)
    except Exception:
        return False
    if not ips:
        return False
    for ip in ips:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        # is_global=False для private/loopback/link-local/reserved/CGNAT (100.64.0.0/10)
        if addr.is_multicast or not addr.is_global:
            return False
    return True


@dataclass
class FetchResult:
    """Результат safe_fetch: текст для LLM-контекста (как раньше) + сырая цепочка редиректов.

    summary -- ровно тот же текст, что раньше возвращался напрямую (включая
    подстроку "redirect chain: ..." при наличии редиректов) -- он идёт в LLM без изменений.
    redirect_chain -- сырой (несанитизированный) список URL цепочки, включая исходный;
    используется только карточкой алерта (там применяется sanitize_redirect_chain).
    """

    summary: str | None
    redirect_chain: list[str] = field(default_factory=list)


async def safe_fetch(url: str) -> FetchResult | None:
    """GET с анти-SSRF, ручным следованием редиректам и лимитами. Вернуть FetchResult или None.

    На каждом hop'е перед запросом проверяем _is_public_host — включая redirect-цели.
    Цепочка редиректов возвращается в результате, чтобы модель видела подмену домена.
    """
    try:
        current = url
        chain: list[str] = []  # redirect-цели, прошедшие SSRF-проверку
        session = await get_session()
        timeout = aiohttp.ClientTimeout(total=settings.LINK_FETCH_TIMEOUT)

        for _ in range(settings.LINK_FETCH_MAX_REDIRECTS + 1):
            parsed = urlparse(current)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                break
            if not await _is_public_host(parsed.hostname):
                logger.warning("Link fetch blocked (non-public host): %s", parsed.hostname)
                break
            # Добавляем в цепочку только redirect-цели (не исходный URL)
            if current != url:
                chain.append(current)

            async with session.get(
                current,
                timeout=timeout,
                allow_redirects=False,
                headers={"User-Agent": "Mozilla/5.0 (compatible; TriggerModerationBot/1.0)"},
            ) as resp:
                if resp.status in (301, 302, 303, 307, 308):
                    location = resp.headers.get("Location")
                    if not location:
                        break
                    current = urljoin(current, location)
                    continue

                if resp.status == 200 and "html" in resp.headers.get("Content-Type", "").lower():
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in resp.content.iter_chunked(65536):
                        total += len(chunk)
                        if total > settings.LINK_FETCH_MAX_BYTES:
                            break
                        chunks.append(chunk)
                    html = b"".join(chunks).decode("utf-8", errors="replace")
                    summary = _extract_summary(html) or None
                    if chain:
                        full_chain = [url, *chain]
                        chain_str = " → ".join(full_chain)
                        text = (
                            f"redirect chain: {chain_str}; final page: {summary}"
                            if summary
                            else f"redirect chain: {chain_str}"
                        )
                        return FetchResult(summary=text, redirect_chain=full_chain)
                    return FetchResult(summary=summary) if summary else None

                break  # не-200 и не-редирект — прекращаем

        # Цикл завершился без итогового 200 html; возвращаем цепочку, если она есть
        if chain:
            full_chain = [url, *chain]
            return FetchResult(summary="redirect chain: " + " → ".join(full_chain), redirect_chain=full_chain)
        return None

    except Exception as e:
        logger.info("Link fetch failed for %s: %s", url, e)
        return None


async def resolve_tg(handle: str) -> str | None:
    """Резолв @username через get_chat: имя, тип, описание. None если не вышло."""
    from app.bot.instance import bot  # noqa: PLC0415 — отложенный импорт для разрыва цикла

    try:
        chat = await bot.get_chat(handle)
        title = chat.title or chat.full_name or handle
        ctype = chat.type
        desc = (getattr(chat, "description", None) or getattr(chat, "bio", None) or "")[:300]
        out = f"{handle} ({ctype}): {title}"
        if desc:
            out += f" — {desc}"
        return out
    except Exception as e:
        logger.info("TG resolve failed for %s: %s", handle, e)
        return None


async def build_link_context(text: str, caption: str) -> tuple[str, list[list[str]]]:
    """Собрать контекст по всем ссылкам из text+caption (≤ LINK_FETCH_MAX_LINKS).

    Возвращает (context_str, redirect_chains): context_str — тот же текст для LLM,
    что и раньше (без изменений); redirect_chains — сырые цепочки редиректов (по одной
    на ссылку, где они были обнаружены), для карточки алерта. ("", []) если ссылок нет.
    """
    if not settings.LINK_ANALYSIS_ENABLED:
        return "", []
    urls, tg = extract_links(f"{text}\n{caption}")
    budget = settings.LINK_FETCH_MAX_LINKS
    lines: list[str] = []
    chains: list[list[str]] = []
    for h in tg[:budget]:
        r = await resolve_tg(h)
        lines.append(f"Telegram {h}: {r}" if r else f"Telegram {h}: (не удалось проверить — недоступно/приватно)")
    remaining = budget - len(lines)
    for u in urls[: max(0, remaining)]:
        fr = await safe_fetch(u)
        if fr and fr.summary:
            lines.append(f"Link {u}: {fr.summary}")
        else:
            lines.append(f"Link {u}: (содержимое недоступно для проверки)")
        if fr and fr.redirect_chain:
            chains.append(fr.redirect_chain)
    return "\n".join(lines), chains
