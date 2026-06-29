"""Анализ ссылок в контенте триггера: извлечение, SSRF-safe фетч, резолв TG-сущностей."""

import asyncio
import contextlib
import ipaddress
import logging
import re
import socket
from html.parser import HTMLParser
from urllib.parse import urlparse

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
    """False, если host резолвится в приватный/loopback/link-local/reserved IP (анти-SSRF)."""
    if host.lower() == "localhost":
        return False
    try:
        ips = await _resolve_ips(host)
    except (socket.gaierror, OSError):
        return False
    if not ips:
        return False
    for ip in ips:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast:
            return False
    return True


async def safe_fetch(url: str) -> str | None:
    """GET с анти-SSRF и лимитами. Вернуть краткую выжимку или None."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    if not await _is_public_host(parsed.hostname):
        logger.warning("Link fetch blocked (non-public host): %s", parsed.hostname)
        return None
    try:
        session = await get_session()
        timeout = aiohttp.ClientTimeout(total=settings.LINK_FETCH_TIMEOUT)
        async with session.get(
            url,
            timeout=timeout,
            allow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0 (compatible; TriggerModerationBot/1.0)"},
        ) as resp:
            if resp.status != 200 or "html" not in resp.headers.get("Content-Type", "").lower():
                return None
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.content.iter_chunked(65536):
                total += len(chunk)
                if total > settings.LINK_FETCH_MAX_BYTES:
                    break
                chunks.append(chunk)
            html = b"".join(chunks).decode("utf-8", errors="replace")
            return _extract_summary(html) or None
    except Exception as e:
        logger.info("Link fetch failed for %s: %s", url, e)
        return None


async def resolve_tg(handle: str) -> str | None:
    """Резолв @username через get_chat: имя, тип, описание. None если не вышло."""
    from app.bot.instance import bot  # noqa: PLC0415 — отложенный импорт для разрыва цикла

    try:
        chat = await bot.get_chat(handle)
    except Exception as e:
        logger.info("TG resolve failed for %s: %s", handle, e)
        return None
    title = chat.title or chat.full_name or handle
    ctype = chat.type
    desc = (getattr(chat, "description", None) or getattr(chat, "bio", None) or "")[:300]
    out = f"{handle} ({ctype}): {title}"
    if desc:
        out += f" — {desc}"
    return out


async def build_link_context(text: str, caption: str) -> str:
    """Собрать контекст по всем ссылкам из text+caption (≤ LINK_FETCH_MAX_LINKS). '' если ссылок нет."""
    if not settings.LINK_ANALYSIS_ENABLED:
        return ""
    urls, tg = extract_links(f"{text}\n{caption}")
    budget = settings.LINK_FETCH_MAX_LINKS
    lines: list[str] = []
    for h in tg[:budget]:
        r = await resolve_tg(h)
        lines.append(f"Telegram {h}: {r}" if r else f"Telegram {h}: (не удалось проверить — недоступно/приватно)")
    remaining = budget - len(lines)
    for u in urls[: max(0, remaining)]:
        s = await safe_fetch(u)
        lines.append(f"Link {u}: {s}" if s else f"Link {u}: (содержимое недоступно для проверки)")
    return "\n".join(lines)
