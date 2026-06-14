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
# Sub-task C: degrade_to_html
# ---------------------------------------------------------------------------

# Теги, которые Telegram plain HTML поддерживает напрямую
_PASSTHROUGH_TAGS: frozenset[str] = frozenset(
    ["b", "i", "u", "s", "code", "pre", "tg-spoiler", "blockquote", "tg-emoji"]
)

# Маппинг rich-тегов → plain Telegram-теги
_TAG_MAP: dict[str, str] = {
    "strong": "b",
    "em": "i",
    "ins": "u",
    "strike": "s",
    "del": "s",
    "aside": "blockquote",
}

# Заголовки h1-h6
_HEADING_RE = re.compile(r"^h[1-6]$")


class _Degrader(HTMLParser):
    """Конвертирует rich-HTML в plain Telegram HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._out: list[str] = []
        # Стек типов списков: "ul" | "ol"
        self._list_stack: list[str] = []
        # Счётчики нумерованных списков (по одному на уровень)
        self._ol_counters: list[int] = []
        # Подавление вывода (для медиа-контента)
        self._suppress_depth: int = 0
        # Буфер для содержимого <li>
        self._in_li: bool = False
        self._li_buf: list[str] = []

    def _emit(self, text: str) -> None:
        """Пишет текст в вывод (с учётом подавления и li-буфера)."""
        if self._suppress_depth > 0:
            return
        if self._in_li:
            self._li_buf.append(text)
        else:
            self._out.append(text)

    def _emit_direct(self, text: str) -> None:
        """Пишет текст напрямую, минуя li-буфер (для маркеров списков)."""
        if self._suppress_depth > 0:
            return
        self._out.append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._handle_open(tag, dict(attrs), self_closing=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._handle_open(tag, dict(attrs), self_closing=True)

    def _handle_open(self, tag: str, attrs: dict[str, str | None], *, self_closing: bool) -> None:
        # Медиа-теги — подавляем сам элемент и его содержимое
        if tag in _MEDIA_TAGS:
            if not self_closing:
                self._suppress_depth += 1
            return

        # tg-map — void, просто выбрасываем
        if tag == "tg-map":
            return

        # tg-collage / tg-slideshow — подавляем содержимое
        if tag in ("tg-collage", "tg-slideshow"):
            if not self_closing:
                self._suppress_depth += 1
            return

        if self._suppress_depth > 0:
            return

        # Заголовки h1-h6 → <b>
        if _HEADING_RE.match(tag):
            self._emit("<b>")
            return

        # br → \n
        if tag == "br":
            self._emit("\n")
            return

        # hr → разделитель
        if tag == "hr":
            self._emit("\n———\n")
            return

        # Списки
        if tag == "ul":
            self._list_stack.append("ul")
            self._ol_counters.append(0)
            return
        if tag == "ol":
            self._list_stack.append("ol")
            self._ol_counters.append(0)
            return
        if tag == "li":
            self._in_li = True
            self._li_buf = []
            return

        # Ссылки
        if tag == "a":
            href = attrs.get("href") or ""
            self._emit(f'<a href="{href}">')
            return

        # tg-emoji — сохраняем с атрибутом
        if tag == "tg-emoji":
            emoji_id = attrs.get("emoji-id") or ""
            self._emit(f'<tg-emoji emoji-id="{emoji_id}">')
            return

        # tg-math / tg-math-block → <code>
        if tag in ("tg-math", "tg-math-block"):
            self._emit("<code>")
            return

        # Passthrough теги
        if tag in _PASSTHROUGH_TAGS:
            self._emit(f"<{tag}>")
            return

        # Маппинг тегов
        if tag in _TAG_MAP:
            mapped = _TAG_MAP[tag]
            self._emit(f"<{mapped}>")
            return

        # Все остальные (p, figure, figcaption, table, tr, td, th, caption,
        # details, summary, footer, cite, tg-reference, tg-time, mark, sub, sup…)
        # — открывающий тег выбрасываем, контент сохраняем

    def handle_endtag(self, tag: str) -> None:
        # Медиа-теги
        if tag in _MEDIA_TAGS:
            if self._suppress_depth > 0:
                self._suppress_depth -= 1
            return

        if tag in ("tg-collage", "tg-slideshow"):
            if self._suppress_depth > 0:
                self._suppress_depth -= 1
            return

        if self._suppress_depth > 0:
            return

        # Заголовки → </b>\n
        if _HEADING_RE.match(tag):
            self._emit("</b>\n")
            return

        # p → двойной перевод строки
        if tag == "p":
            self._emit("\n\n")
            return

        # Списки
        if tag in ("ul", "ol"):
            if self._list_stack:
                self._list_stack.pop()
                self._ol_counters.pop()
            return
        if tag == "li":
            content = "".join(self._li_buf)
            self._in_li = False
            self._li_buf = []
            if self._list_stack and self._list_stack[-1] == "ol":
                self._ol_counters[-1] += 1
                num = self._ol_counters[-1]
                self._emit_direct(f"{num}. {content}\n")
            else:
                self._emit_direct(f"• {content}\n")
            return

        # Ссылки
        if tag == "a":
            self._emit("</a>")
            return

        # tg-emoji
        if tag == "tg-emoji":
            self._emit("</tg-emoji>")
            return

        # tg-math / tg-math-block → </code>
        if tag in ("tg-math", "tg-math-block"):
            self._emit("</code>")
            return

        # Passthrough
        if tag in _PASSTHROUGH_TAGS:
            self._emit(f"</{tag}>")
            return

        # Маппинг
        if tag in _TAG_MAP:
            mapped = _TAG_MAP[tag]
            self._emit(f"</{mapped}>")
            return

        # Остальное — закрывающий тег выбрасываем, контент уже в выводе

    def handle_data(self, data: str) -> None:
        self._emit(data)

    def handle_entityref(self, name: str) -> None:
        self._emit(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._emit(f"&#{name};")

    def result(self) -> str:
        return "".join(self._out)


def degrade_to_html(html: str) -> str:
    """
    Конвертирует rich-HTML (Bot API 10.1) в plain Telegram HTML.

    Поддерживаемые Telegram-теги (b, i, u, s, code, pre, tg-spoiler,
    blockquote, tg-emoji, a) — сохраняются. Остальное деградирует по правилам:
    strong→b, em→i, ins→u, strike/del→s, aside→blockquote,
    h1-h6→<b>…</b>+'\n', p→text+'\n\n', ul/ol/li→маркеры,
    br→'\n', hr→'\n———\n', tg-math→<code>, медиа удаляются.
    """
    parser = _Degrader()
    parser.feed(html)
    return parser.result()
