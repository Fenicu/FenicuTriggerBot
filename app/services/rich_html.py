"""
Утилиты для работы с Bot API 10.1 rich-HTML сообщениями.

Публичные функции:
  validate_rich_html(html) -> None  — валидирует, бросает RichHtmlError
  degrade_to_html(html)   -> str   — конвертирует rich-HTML в plain Telegram HTML
"""

from __future__ import annotations

import html as _html
import re
from html.parser import HTMLParser
from urllib.parse import quote

# ---------------------------------------------------------------------------
# Константы контракта
# ---------------------------------------------------------------------------

_INLINE_TAGS: frozenset[str] = frozenset(
    [
        "b",
        "strong",
        "i",
        "em",
        "u",
        "ins",
        "s",
        "strike",
        "del",
        "code",
        "mark",
        "sub",
        "sup",
        "tg-spoiler",
        "a",
        "tg-reference",
        "tg-emoji",
        "tg-time",
        "tg-math",
        "br",
        "cite",
    ]
)

_BLOCK_TAGS: frozenset[str] = frozenset(
    [
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "p",
        "pre",
        "footer",
        "hr",
        "ul",
        "ol",
        "li",
        "input",
        "blockquote",
        "aside",
        "img",
        "video",
        "audio",
        "figure",
        "figcaption",
        "tg-map",
        "tg-collage",
        "tg-slideshow",
        "table",
        "caption",
        "tr",
        "th",
        "td",
        "details",
        "summary",
        "tg-math-block",
    ]
)

_ALL_TAGS: frozenset[str] = _INLINE_TAGS | _BLOCK_TAGS

# Void-теги: нет закрывающего, не кладутся в стек
_VOID_TAGS: frozenset[str] = frozenset(["br", "hr", "img", "input", "tg-map"])

# Разрешённые именованные HTML-сущности
_ALLOWED_NAMED_ENTITIES: frozenset[str] = frozenset(
    [
        "lt",
        "gt",
        "amp",
        "quot",
        "apos",
        "nbsp",
        "hellip",
        "mdash",
        "ndash",
        "lsquo",
        "rsquo",
        "ldquo",
        "rdquo",
    ]
)

# Теги, считающиеся "блоками" для лимита ≤500
_BLOCK_COUNT_TAGS: frozenset[str] = frozenset(
    [
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "p",
        "pre",
        "footer",
        "ul",
        "ol",
        "li",
        "blockquote",
        "aside",
        "figure",
        "table",
        "tr",
        "details",
        "tg-collage",
        "tg-slideshow",
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


class _RichHtmlValidator(HTMLParser):
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
                raise RichHtmlError(f"<{tag}> src must be an http/https URL, got: {src!r}")

        # Колонки таблицы
        if tag == "tr":
            self._col_count = 0
        elif tag in ("td", "th") and self._col_count is not None:
            self._col_count += 1
            if self._col_count > _MAX_COLUMNS:
                raise RichHtmlError(f"table row column count exceeds limit of {_MAX_COLUMNS}")

    def _push(self, tag: str) -> None:
        """Кладёт тег в стек, проверяет максимальную глубину."""
        self._stack.append(tag)
        depth = len(self._stack)
        if depth > _MAX_DEPTH:
            raise RichHtmlError(f"nesting depth {depth} exceeds limit of {_MAX_DEPTH} levels")

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
        # Сбрасываем счётчик колонок при закрытии строки таблицы
        if tag == "tr":
            self._col_count = None
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
        # Длина считается в Unicode-кодопоинтах (len(str)), что соответствует
        # лимиту Bot API в 32768 символов; entity/charref ниже считаются как 1 символ.
        self._char_count += len(data)
        if self._char_count > _MAX_CHARS:
            raise RichHtmlError(f"text length exceeds limit of {_MAX_CHARS} characters")

    def handle_entityref(self, name: str) -> None:
        if name not in _ALLOWED_NAMED_ENTITIES:
            raise RichHtmlError(f"unsupported entity: {name}")
        # Именованная сущность декодируется в один символ — считаем как 1 кодопоинт
        self._char_count += 1
        if self._char_count > _MAX_CHARS:
            raise RichHtmlError(f"text length exceeds limit of {_MAX_CHARS} characters")

    def handle_charref(self, name: str) -> None:
        # Числовая ссылка (&#N; или &#xN;) — один символ, считаем как 1 кодопоинт
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
    parser = _RichHtmlValidator()
    parser.feed(html)
    parser.close()


# ---------------------------------------------------------------------------
# Sub-task C: degrade_to_html
# ---------------------------------------------------------------------------

# Теги, которые Telegram plain HTML поддерживает напрямую.
# tg-emoji здесь не перечислен — он требует передачи атрибута emoji-id,
# поэтому обрабатывается отдельно в _handle_open / handle_endtag.
_PASSTHROUGH_TAGS: frozenset[str] = frozenset(["b", "i", "u", "s", "code", "pre", "tg-spoiler", "blockquote"])

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
    """Конвертирует rich-HTML в plain Telegram HTML.

    Принимает уже провалидированный rich-HTML (предполагается корректная
    вложенность и разрешённые теги). Suppress-механизм применяется только
    к медиа-контейнерам (video/audio с телом, tg-collage, tg-slideshow).
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._out: list[str] = []
        # Стек типов списков: "ul" | "ol"
        self._list_stack: list[str] = []
        # Счётчики нумерованных списков (по одному на уровень).
        # ul тоже пушит 0 — чтобы индексы всегда совпадали с _list_stack.
        self._ol_counters: list[int] = []
        # Подавление вывода (для медиа-контента)
        self._suppress_depth: int = 0
        # Стек буферов для содержимого вложенных <li>
        self._li_stack: list[list[str]] = []

    def _emit(self, text: str) -> None:
        """Пишет текст в вывод (с учётом подавления и li-буфера)."""
        if self._suppress_depth > 0:
            return
        if self._li_stack:
            self._li_stack[-1].append(text)
        else:
            self._out.append(text)

    def _emit_direct(self, text: str) -> None:
        """Пишет текст напрямую в _out, минуя li-буфер (для маркеров списков)."""
        if self._suppress_depth > 0:
            return
        self._out.append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._handle_open(tag, dict(attrs), self_closing=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._handle_open(tag, dict(attrs), self_closing=True)

    def _handle_open(self, tag: str, attrs: dict[str, str | None], *, self_closing: bool) -> None:
        # Медиа-теги — подавляем сам элемент и его содержимое.
        # Void-теги (img) никогда не получают закрывающего тега — suppress не трогаем.
        # Только non-void non-self-closing (video/audio с контентом) → suppress++.
        if tag in _MEDIA_TAGS:
            if not self_closing and tag not in _VOID_TAGS:
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
            # ul пушит 0 наравне с ol — чтобы _ol_counters синхронизирован с _list_stack
            self._ol_counters.append(0)
            return
        if tag == "ol":
            self._list_stack.append("ol")
            self._ol_counters.append(0)
            return
        if tag == "li":
            self._li_stack.append([])
            return

        # Ссылки
        if tag == "a":
            href = _html.escape(attrs.get("href") or "", quote=True)
            self._emit(f'<a href="{href}">')
            return

        # tg-emoji — сохраняем с атрибутом (обрабатывается отдельно от _PASSTHROUGH_TAGS)
        if tag == "tg-emoji":
            emoji_id = _html.escape(attrs.get("emoji-id") or "", quote=True)
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
        # Медиа-теги и контейнеры-подавители — уменьшаем глубину suppress
        if tag in _MEDIA_TAGS or tag in ("tg-collage", "tg-slideshow"):
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
            if self._li_stack:
                buf = self._li_stack.pop()
                content = "".join(buf)
            else:
                content = ""
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

    Принимает уже провалидированный rich-HTML. Поддерживаемые Telegram-теги
    (b, i, u, s, code, pre, tg-spoiler, blockquote, tg-emoji, a) — сохраняются.
    Остальное деградирует по правилам: strong→b, em→i, ins→u, strike/del→s,
    aside→blockquote, h1-h6→<b>…</b>+'\n', p→text+'\n\n', ul/ol/li→маркеры,
    br→'\n', hr→'\n———\n', tg-math→<code>, медиа удаляются.
    """
    parser = _Degrader()
    parser.feed(html)
    return parser.result()


# ---------------------------------------------------------------------------
# Sub-task D: rich_message → rich-HTML (обратное к degrade)
# ---------------------------------------------------------------------------


def _esc(text: str) -> str:
    """Экранирование текстового содержимого (&<>)."""
    return _html.escape(text, quote=False)


def _esc_attr(value: str) -> str:
    """Экранирование значения атрибута (& < > \" ')."""
    return _html.escape(value, quote=True)


# inline-обёртки с единственным дочерним .text → (открывающий, закрывающий) тег
_INLINE_WRAP: dict[str, tuple[str, str]] = {
    "bold": ("<b>", "</b>"),
    "italic": ("<i>", "</i>"),
    "underline": ("<u>", "</u>"),
    "strikethrough": ("<s>", "</s>"),
    "spoiler": ("<tg-spoiler>", "</tg-spoiler>"),
    "code": ("<code>", "</code>"),
    "marked": ("<mark>", "</mark>"),
    "subscript": ("<sub>", "</sub>"),
    "superscript": ("<sup>", "</sup>"),
}


def _richtext_to_html(node: object) -> str:
    """Рекурсивно сериализует RichTextUnion (str | list | typed-node) в rich-HTML."""
    if isinstance(node, str):
        return _esc(node)
    if isinstance(node, list):
        return "".join(_richtext_to_html(child) for child in node)

    node_type = getattr(node, "type", None)

    if node_type in _INLINE_WRAP:
        open_t, close_t = _INLINE_WRAP[node_type]
        return f"{open_t}{_richtext_to_html(node.text)}{close_t}"

    if node_type == "url":
        return f'<a href="{_esc_attr(node.url)}">{_richtext_to_html(node.text)}</a>'

    if node_type == "text_mention":
        return f'<a href="tg://user?id={node.user.id}">{_richtext_to_html(node.text)}</a>'

    if node_type == "custom_emoji":
        return f'<tg-emoji emoji-id="{_esc_attr(node.custom_emoji_id)}">{_esc(node.alternative_text)}</tg-emoji>'

    if node_type == "mathematical_expression":
        return f"<tg-math>{_esc(node.expression)}</tg-math>"

    if node_type == "anchor":
        return ""

    # date_time / mention / hashtag / cashtag / bot_command / phone_number /
    # email_address / bank_card_number / reference / reference_link / anchor_link
    # — авто-детектируемые сущности: отдаём внутренний текст plain.
    inner = getattr(node, "text", None)
    if inner is not None:
        return _richtext_to_html(inner)
    return ""


def _caption_html(caption: object) -> str:
    """RichBlockCaption | None → '<p>…</p>' либо ''."""
    if caption is None:
        return ""
    text = getattr(caption, "text", None)
    if text is None:
        return ""
    return f"<p>{_richtext_to_html(text)}</p>"


def _media_url(base: str, file_id: str) -> str:
    return f"{base.rstrip('/')}/media/proxy?file_id={quote(file_id)}"


def _largest_photo_id(photo: list) -> str:
    return max(photo, key=lambda p: p.width or 0).file_id


def _richblock_to_html(block: object, media_base_url: str | None) -> str:
    bt = block.type

    if bt == "paragraph":
        return f"<p>{_richtext_to_html(block.text)}</p>"
    if bt == "heading":
        size = min(6, max(1, block.size))
        return f"<h{size}>{_richtext_to_html(block.text)}</h{size}>"
    if bt == "pre":
        return f"<pre>{_richtext_to_html(block.text)}</pre>"
    if bt == "footer":
        return f"<footer>{_richtext_to_html(block.text)}</footer>"
    if bt == "divider":
        return "<hr>"
    if bt == "mathematical_expression":
        return f"<tg-math-block>{_esc(block.expression)}</tg-math-block>"
    if bt == "thinking":
        return f"<blockquote><p>{_richtext_to_html(block.text)}</p></blockquote>"

    if bt == "blockquote":
        inner = "".join(_richblock_to_html(b, media_base_url) for b in block.blocks)
        if block.credit is not None:
            inner += f"<footer>{_richtext_to_html(block.credit)}</footer>"
        return f"<blockquote>{inner}</blockquote>"
    if bt == "pullquote":
        inner = _richtext_to_html(block.text)
        if block.credit is not None:
            inner += f"<footer>{_richtext_to_html(block.credit)}</footer>"
        return f"<aside>{inner}</aside>"

    if bt == "list":
        items = block.items
        is_checklist = any(it.has_checkbox for it in items)
        is_ordered = not is_checklist and any(it.value is not None for it in items)
        if is_ordered:
            ol_type = next((it.type for it in items if it.type), None)
            type_attr = f' type="{_esc_attr(ol_type)}"' if ol_type else ""
            lis = []
            for it in items:
                val_attr = f' value="{it.value}"' if it.value is not None else ""
                inner = "".join(_richblock_to_html(b, media_base_url) for b in it.blocks)
                lis.append(f"<li{val_attr}>{inner}</li>")
            return f"<ol{type_attr}>{''.join(lis)}</ol>"
        lis = []
        for it in items:
            inner = "".join(_richblock_to_html(b, media_base_url) for b in it.blocks)
            if it.has_checkbox:
                inner = ('<input type="checkbox" checked>' if it.is_checked else '<input type="checkbox">') + inner
            lis.append(f"<li>{inner}</li>")
        return f"<ul>{''.join(lis)}</ul>"

    if bt == "details":
        inner = "".join(_richblock_to_html(b, media_base_url) for b in block.blocks)
        return f"<details><summary>{_richtext_to_html(block.summary)}</summary>{inner}</details>"

    if bt == "table":
        rows = []
        for row in block.cells:
            parts = []
            for cell in row:
                tag = "th" if cell.is_header else "td"
                attrs = f' align="{_esc_attr(cell.align)}" valign="{_esc_attr(cell.valign)}"'
                if cell.colspan is not None and cell.colspan > 1:
                    attrs += f' colspan="{cell.colspan}"'
                if cell.rowspan is not None and cell.rowspan > 1:
                    attrs += f' rowspan="{cell.rowspan}"'
                content = _richtext_to_html(cell.text) if cell.text is not None else ""
                parts.append(f"<{tag}{attrs}>{content}</{tag}>")
            rows.append(f"<tr>{''.join(parts)}</tr>")
        caption = f"<caption>{_richtext_to_html(block.caption)}</caption>" if block.caption is not None else ""
        table_attrs = ""
        if block.is_bordered:
            table_attrs += " bordered"
        if block.is_striped:
            table_attrs += " striped"
        return f"<table{table_attrs}>{caption}{''.join(rows)}</table>"

    if bt in ("collage", "slideshow"):
        tag = "tg-collage" if bt == "collage" else "tg-slideshow"
        inner = "".join(_richblock_to_html(b, media_base_url) for b in block.blocks)
        return f"<{tag}>{inner}</{tag}>{_caption_html(block.caption)}"

    # медиа-блоки
    if bt == "photo":
        body = (
            f'<img src="{_media_url(media_base_url, _largest_photo_id(block.photo))}">'
            if media_base_url and block.photo
            else ""
        )
        return body + _caption_html(block.caption)
    if bt in ("video", "animation"):
        fid = block.video.file_id if bt == "video" else block.animation.file_id
        body = f'<video src="{_media_url(media_base_url, fid)}"></video>' if media_base_url else ""
        return body + _caption_html(block.caption)
    if bt == "audio":
        body = f'<audio src="{_media_url(media_base_url, block.audio.file_id)}"></audio>' if media_base_url else ""
        return body + _caption_html(block.caption)
    if bt == "voice_note":
        body = f'<audio src="{_media_url(media_base_url, block.voice_note.file_id)}"></audio>' if media_base_url else ""
        return body + _caption_html(block.caption)

    if bt == "map":
        return _caption_html(block.caption)

    # anchor и любые неизвестные будущие типы — выбрасываем
    return ""


def rich_message_to_html(rich_message: object, *, media_base_url: str | None = None) -> str:
    """
    Сериализует aiogram RichMessage (Bot API 10.1) в rich-HTML.

    Обратное к degrade_to_html: дерево blocks/RichText → теги из контракта
    rich-HTML. Медиа-блоки получают src через media proxy (нужен media_base_url
    вида 'https://host/api/v1'); без него медиа выбрасываются, остаётся caption.
    Anchor/map выбрасываются (нет совместимого тега). Результат предназначен
    для validate_rich_html + InputRichMessage(html=...).
    """
    return "".join(_richblock_to_html(b, media_base_url) for b in rich_message.blocks)
