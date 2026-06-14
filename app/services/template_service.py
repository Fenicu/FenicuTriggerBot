import html
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import markupsafe
from aiogram.types import Chat, User
from jinja2 import nodes
from jinja2.sandbox import SandboxedEnvironment

from app.core.time_util import get_timezone


def mention_filter(value: str) -> str:
    """
    Превращает ID или username в HTML-ссылку для Telegram.
    Если значение состоит из цифр - считается ID пользователя.
    Иначе - username.
    """
    if value.isdigit():
        return f'<a href="tg://user?id={value}">{value}</a>'
    return f'<a href="https://t.me/{value}">{value}</a>'


def html_filter(value: str) -> str:
    """Экранирует HTML-символы."""
    return html.escape(value)


def bold_filter(value: str) -> str:
    """Форматирует текст как жирный в Telegram HTML."""
    return f"<b>{value}</b>"


def italic_filter(value: str) -> str:
    """Форматирует текст как курсив в Telegram HTML."""
    return f"<i>{value}</i>"


def code_filter(value: str) -> str:
    """Форматирует текст как код в Telegram HTML."""
    return f"<code>{value}</code>"


# Окружение без автоэкранирования — для render_template (plain-шаблоны)
env = SandboxedEnvironment()
env.filters["mention"] = mention_filter
env.filters["html"] = html_filter
env.filters["bold"] = bold_filter
env.filters["italic"] = italic_filter
env.filters["code"] = code_filter


# ---------------------------------------------------------------------------
# Окружение с autoescape=True — для render_rich_template
# Подстановочные переменные автоматически экранируются; литеральный HTML
# шаблона остаётся нетронутым. Фильтры, генерирующие теги, возвращают
# markupsafe.Markup, чтобы Jinja не экранировал их повторно.
# ---------------------------------------------------------------------------


def _rich_mention_filter(value: str) -> markupsafe.Markup:
    """Mention-фильтр для rich-среды: возвращает Markup (безопасный HTML)."""
    escaped = markupsafe.escape(value)
    if str(value).isdigit():
        return markupsafe.Markup(f'<a href="tg://user?id={escaped}">{escaped}</a>')  # noqa: S704
    return markupsafe.Markup(f'<a href="https://t.me/{escaped}">{escaped}</a>')  # noqa: S704


def _rich_html_filter(value: str) -> markupsafe.Markup:
    """html-фильтр в rich-среде — экранирует, возвращает Markup (Jinja не экранирует повторно)."""
    return markupsafe.Markup(markupsafe.escape(value))  # noqa: S704


def _rich_bold_filter(value: str) -> markupsafe.Markup:
    """bold в rich-среде: значение экранируется, тег <b> остаётся реальным."""
    return markupsafe.Markup(f"<b>{markupsafe.escape(value)}</b>")  # noqa: S704


def _rich_italic_filter(value: str) -> markupsafe.Markup:
    """italic в rich-среде."""
    return markupsafe.Markup(f"<i>{markupsafe.escape(value)}</i>")  # noqa: S704


def _rich_code_filter(value: str) -> markupsafe.Markup:
    """code в rich-среде."""
    return markupsafe.Markup(f"<code>{markupsafe.escape(value)}</code>")  # noqa: S704


_rich_env = SandboxedEnvironment(autoescape=True)
_rich_env.filters["mention"] = _rich_mention_filter
_rich_env.filters["html"] = _rich_html_filter
_rich_env.filters["bold"] = _rich_bold_filter
_rich_env.filters["italic"] = _rich_italic_filter
_rich_env.filters["code"] = _rich_code_filter
# Убираем фильтры, которые возвращают сырую разметку в обход autoescape.
# |safe позволяет пользователю через vars.* внедрить произвольный HTML (XSS).
_rich_env.filters.pop("safe", None)


def _check_no_loops(node: nodes.Node) -> None:
    """
    Рекурсивно проверяет AST шаблона на отсутствие циклов.
    Вызывает ValueError при обнаружении for.
    """
    if isinstance(node, nodes.For):
        raise ValueError("Циклы запрещены в шаблонах")
    for child in node.iter_child_nodes():
        _check_no_loops(child)


def validate_template(template_str: str) -> None:
    """
    Валидирует шаблон на отсутствие циклов.
    Вызывает ValueError если найдены циклы.
    """
    ast = env.parse(template_str)
    _check_no_loops(ast)


def render_template(template_str: str, context: dict[str, Any]) -> str:
    """
    Рендерит шаблон с предоставленным контекстом.
    Сначала валидирует шаблон на отсутствие циклов.
    Возвращает отрендеренную строку.
    """
    validate_template(template_str)
    template = env.from_string(template_str)
    return template.render(**context)


def render_rich_template(template_str: str, context: dict[str, Any]) -> str:
    """
    Рендерит rich-HTML шаблон с autoescape.

    Литеральные теги в шаблоне сохраняются нетронутыми, а подставляемые
    значения переменных HTML-экранируются автоматически (autoescape=True).

    Исключение: user.mention — намеренный HTML-линк; если передан как
    обычная строка, оборачивается в markupsafe.Markup автоматически.
    Фильтры bold/italic/code/mention тоже возвращают Markup — реальные теги
    сохраняются, но переданные в них значения экранируются внутри фильтра.

    Валидация циклов выполняется через тот же _check_no_loops (используется
    парсер _rich_env).
    """
    # Копируем user-словарь, чтобы не мутировать оригинал, и помечаем
    # mention как безопасный HTML — Jinja не будет его экранировать.
    ctx = dict(context)
    if isinstance(ctx.get("user"), dict) and "mention" in ctx["user"]:
        user_ctx = dict(ctx["user"])
        mention = user_ctx["mention"]
        if not isinstance(mention, markupsafe.Markup):
            user_ctx["mention"] = markupsafe.Markup(mention)  # noqa: S704
        ctx["user"] = user_ctx

    ast = _rich_env.parse(template_str)
    _check_no_loops(ast)
    template = _rich_env.from_string(template_str)
    return template.render(**ctx)


def get_render_context(
    user: User,
    chat: Chat,
    variables: dict[str, Any] | None = None,
    timezone: str | ZoneInfo | None = None,
) -> dict[str, Any]:
    """
    Создает контекст для рендеринга шаблонов.
    """
    if timezone is None:
        tz = get_timezone()
    elif isinstance(timezone, str):
        tz = ZoneInfo(timezone)
    else:
        tz = timezone
    now = datetime.now(tz)

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "first_name": user.first_name,
            "mention": markupsafe.Markup(  # noqa: S704
                f'<a href="tg://user?id={user.id}">{markupsafe.escape(user.full_name)}</a>'
            ),
        },
        "chat": {
            "id": chat.id,
            "title": chat.title,
        },
        "date": now.strftime("%d.%m.%Y"),
        "time": now.strftime("%H:%M"),
        "now": now,
        "vars": variables or {},
    }
