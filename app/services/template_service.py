import html
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

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


def get_render_context(
    user: User,
    chat: Chat,
    variables: dict[str, Any] | None = None,
    timezone: ZoneInfo | None = None,
) -> dict[str, Any]:
    """
    Создает контекст для рендеринга шаблонов.
    """
    tz = timezone if timezone else get_timezone()
    now = datetime.now(tz)

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "first_name": user.first_name,
            "mention": f'<a href="tg://user?id={user.id}">{user.full_name}</a>',
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
