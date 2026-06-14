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

# Теги, считающиеся "блоками" для лимита ≤500
_BLOCK_COUNT_TAGS: frozenset[str] = frozenset(
    [
        "h1", "h2", "h3", "h4", "h5", "h6",
        "p", "pre", "footer",
        "ul", "ol", "li",
        "blockquote", "aside",
        "figure", "table", "tr",
        "details", "tg-collage", "tg-slideshow",
    ]
)

# Медиа-теги для лимита ≤50
_MEDIA_TAGS: frozenset[str] = frozenset(["img", "video", "audio"])

# Лимиты
_MAX_CHARS = 32768
_MAX_BLOCKS = 500
_MAX_DEPTH = 16
_MAX_MEDIA = 50
_MAX_COLUMNS = 20


# ---------------------------------------------------------------------------
# Исключение
# ---------------------------------------------------------------------------


class RichHtmlError(ValueError):
    """Нарушение контракта rich-HTML."""


# ---------------------------------------------------------------------------
# Sub-task A+B: валидатор — теги, сущности, вложенность, лимиты, src медиа
# ---------------------------------------------------------------------------


class _ValidatorA(HTMLParser):
    """Проверяет теги, сущности, вложенность, лимиты и src медиа-тегов."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        # Стек тегов для проверки вложенности
        self._stack: list[str] = []
        # Счётчики лимитов
        self._char_count: int = 0
        self._block_count: int = 0
        self._media_count: int = 0
        # Счётчик колонок текущей строки таблицы (None — вне <tr>)
        self._col_count: int | None = None

    def _check_tag(self, tag: str) -> None:
        if tag not in _ALL_TAGS:
            raise RichHtmlError(f"unsupported tag: {tag}")

    def _account_tag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Общая бухгалтерия для открывающего/void/self-closing тега."""
        # Блоки
        if tag in _BLOCK_COUNT_TAGS:
            self._block_count += 1
            if self._block_count > _MAX_BLOCKS:
                raise RichHtmlError(f"block count exceeds limit of {_MAX_BLOCKS}")

        # Медиа
        if tag in _MEDIA_TAGS:
            self._media_count += 1
            if self._media_count > _MAX_MEDIA:
                raise RichHtmlError(f"media count exceeds limit of {_MAX_MEDIA}")
            attr_dict = dict(attrs)
            src = attr_dict.get("src", "") or ""
            if not re.match(r"^https?://", src):
                raise RichHtmlError(
                    f"<{tag}> src must be an http/https URL, got: {src!r}"
                )

        # Колонки таблицы
        if tag == "tr":
            self._col_count = 0
        elif tag in ("td", "th"):
            if self._col_count is not None:
                self._col_count += 1
                if self._col_count > _MAX_COLUMNS:
                    raise RichHtmlError(
                        f"table row column count exceeds limit of {_MAX_COLUMNS}"
                    )

    def _push(self, tag: str) -> None:
        """Кладёт тег в стек, проверяет максимальную глубину."""
        self._stack.append(tag)
        depth = len(self._stack)
        if depth > _MAX_DEPTH:
            raise RichHtmlError(
                f"nesting depth {depth} exceeds limit of {_MAX_DEPTH} levels"
            )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._check_tag(tag)
        self._account_tag(tag, attrs)
        if tag not in _VOID_TAGS:
            self._push(tag)

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
        """Самозакрывающиеся теги вида <tag/> — та же бухгалтерия, стек не трогаем."""
        self._check_tag(tag)
        self._account_tag(tag, attrs)

    def handle_data(self, data: str) -> None:
        self._char_count += len(data)
        if self._char_count > _MAX_CHARS:
            raise RichHtmlError(f"text length exceeds limit of {_MAX_CHARS} characters")

    def handle_entityref(self, name: str) -> None:
        if name not in _ALLOWED_NAMED_ENTITIES:
            raise RichHtmlError(f"unsupported entity: {name}")
        self._char_count += 1
        if self._char_count > _MAX_CHARS:
            raise RichHtmlError(f"text length exceeds limit of {_MAX_CHARS} characters")

    def handle_charref(self, name: str) -> None:
        self._char_count += 1
        if self._char_count > _MAX_CHARS:
            raise RichHtmlError(f"text length exceeds limit of {_MAX_CHARS} characters")

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
