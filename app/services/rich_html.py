"""
Утилиты для работы с Bot API 10.1 rich-HTML сообщениями.

Публичные функции:
  validate_rich_html(html) -> None  — валидирует, бросает RichHtmlError
  degrade_to_html(html)   -> str   — конвертирует rich-HTML в plain Telegram HTML
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# Константы контракта
# ---------------------------------------------------------------------------

_INLINE_TAGS: frozenset[str] = frozenset(
    [
        "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
        "code", "mark", "sub", "sup",
        "tg-spoiler", "a", "tg-reference", "tg-emoji", "tg-time",
        "tg-math", "br", "cite",
    ]
)

_BLOCK_TAGS: frozenset[str] = frozenset(
    [
        "h1", "h2", "h3", "h4", "h5", "h6",
        "p", "pre", "footer", "hr",
        "ul", "ol", "li",
        "input", "blockquote", "aside",
        "img", "video", "audio",
        "figure", "figcaption",
        "tg-map", "tg-collage", "tg-slideshow",
        "table", "caption", "tr", "th", "td",
        "details", "summary",
        "tg-math-block",
    ]
)

_ALL_TAGS: frozenset[str] = _INLINE_TAGS | _BLOCK_TAGS

# Void-теги: нет закрывающего, не кладутся в стек
_VOID_TAGS: frozenset[str] = frozenset(["br", "hr", "img", "input", "tg-map"])

# Разрешённые именованные HTML-сущности
_ALLOWED_NAMED_ENTITIES: frozenset[str] = frozenset(
    [
        "lt", "gt", "amp", "quot", "apos", "nbsp",
        "hellip", "mdash", "ndash",
        "lsquo", "rsquo", "ldquo", "rdquo",
    ]
)


# ---------------------------------------------------------------------------
# Исключение
# ---------------------------------------------------------------------------


class RichHtmlError(ValueError):
    """Нарушение контракта rich-HTML."""


# ---------------------------------------------------------------------------
# Sub-task A: валидатор — теги, сущности, вложенность
# ---------------------------------------------------------------------------


class _ValidatorA(HTMLParser):
    """Проверяет разрешённые теги, сущности и корректность вложенности."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._stack: list[str] = []

    def _check_tag(self, tag: str) -> None:
        if tag not in _ALL_TAGS:
            raise RichHtmlError(f"unsupported tag: {tag}")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._check_tag(tag)
        if tag not in _VOID_TAGS:
            self._stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _VOID_TAGS:
            return
        if tag not in _ALL_TAGS:
            raise RichHtmlError(f"unsupported tag: {tag}")
        if not self._stack:
            raise RichHtmlError(f"mismatched </{tag}>: stack is empty")
        top = self._stack[-1]
        if top != tag:
            raise RichHtmlError(f"mismatched </{tag}>: expected </{top}>")
        self._stack.pop()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._check_tag(tag)

    def handle_entityref(self, name: str) -> None:
        if name not in _ALLOWED_NAMED_ENTITIES:
            raise RichHtmlError(f"unsupported entity: {name}")

    def handle_charref(self, name: str) -> None:
        pass  # числовые сущности всегда разрешены

    def close(self) -> None:
        super().close()
        if self._stack:
            raise RichHtmlError(f"unclosed <{self._stack[-1]}>")


def validate_rich_html(html: str) -> None:
    """
    Валидирует rich-HTML строку согласно контракту Bot API 10.1.

    Бросает RichHtmlError при нарушении любого правила.
    """
    parser = _ValidatorA()
    parser.feed(html)
    parser.close()


# ---------------------------------------------------------------------------
# Sub-task C: заглушка (будет реализована в следующем коммите)
# ---------------------------------------------------------------------------


def degrade_to_html(html: str) -> str:
    """Конвертирует rich-HTML в plain Telegram HTML (заглушка)."""
    raise NotImplementedError
