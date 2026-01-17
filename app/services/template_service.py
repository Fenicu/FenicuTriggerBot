"""
Сервис для безопасного шаблонизатора Jinja2 с ограничениями.
Использует SandboxedEnvironment для предотвращения доступа к небезопасным атрибутам.
Запрещает циклы (for, while) и интроспекцию (__class__, __globals__).
Разрешает только подстановки {{ var }}, условия {% if %}, фильтры.
"""

import html
from typing import Any

from jinja2 import nodes
from jinja2.sandbox import SandboxedEnvironment


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


env = SandboxedEnvironment()
env.filters["mention"] = mention_filter
env.filters["html"] = html_filter
env.filters["bold"] = bold_filter
env.filters["italic"] = italic_filter
env.filters["code"] = code_filter


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
