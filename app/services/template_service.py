from __future__ import annotations

import asyncio
import html
import math
import multiprocessing
import resource
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from datetime import datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import markupsafe
from jinja2 import nodes
from jinja2.runtime import Context
from jinja2.sandbox import SandboxedEnvironment

if TYPE_CHECKING:
    from aiogram.types import Chat, User

_MAX_MULTIPLIER = 10_000
_MAX_RENDERED_LENGTH = 8_192
_RENDER_TIMEOUT_SECONDS = 1.0
_WORKER_MEMORY_BYTES = 256 * 1024 * 1024
_WORKER_CPU_SECONDS = 2
_RENDER_WORKERS = 2


class _LimitedSandbox(SandboxedEnvironment):
    intercepted_binops = frozenset({"*", "+"})

    def call_binop(self, context: Context, operator: str, left: Any, right: Any) -> Any:
        sequence_types = (str, list, tuple)
        if operator == "*":
            sequence, count = (right, left) if isinstance(left, int) else (left, right)
            if (
                isinstance(sequence, sequence_types)
                and isinstance(count, int)
                and len(sequence) * max(0, count) > _MAX_RENDERED_LENGTH
            ):
                raise ValueError("Слишком длинный результат шаблона")
        elif isinstance(left, sequence_types) and isinstance(right, type(left)):
            if len(left) + len(right) > _MAX_RENDERED_LENGTH:
                raise ValueError("Слишком длинный результат шаблона")
        result = super().call_binop(context, operator, left, right)
        if isinstance(result, sequence_types) and len(result) > _MAX_RENDERED_LENGTH:
            raise ValueError("Слишком длинный результат шаблона")
        return result


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
env = _LimitedSandbox()
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


_rich_env = _LimitedSandbox(autoescape=True)
_rich_env.filters["mention"] = _rich_mention_filter
_rich_env.filters["html"] = _rich_html_filter
_rich_env.filters["bold"] = _rich_bold_filter
_rich_env.filters["italic"] = _rich_italic_filter
_rich_env.filters["code"] = _rich_code_filter
# Убираем фильтры, которые возвращают сырую разметку в обход autoescape.
# |safe позволяет пользователю через vars.* внедрить произвольный HTML (XSS).
_rich_env.filters.pop("safe", None)


_render_pool: ProcessPoolExecutor | None = None


def _initialize_render_worker() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (_WORKER_MEMORY_BYTES, _WORKER_MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_CPU, (_WORKER_CPU_SECONDS, resource.RLIM_INFINITY))


def _get_render_pool() -> ProcessPoolExecutor:
    global _render_pool  # noqa: PLW0603
    if _render_pool is None:
        _render_pool = ProcessPoolExecutor(
            max_workers=_RENDER_WORKERS,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=_initialize_render_worker,
        )
    return _render_pool


def _reset_render_pool(pool: ProcessPoolExecutor) -> None:
    global _render_pool  # noqa: PLW0603
    if _render_pool is not pool:
        return
    _render_pool = None
    # kill_workers появился в Python 3.14; проект поддерживает также 3.13.
    workers = list((pool._processes or {}).values())
    for worker in workers:
        if worker.is_alive():
            worker.kill()
    pool.shutdown(wait=True, cancel_futures=True)
    for worker in workers:
        worker.join()


def _render_in_worker(template_str: str, context: dict[str, Any], rich: bool) -> str:
    # Лимит CPU считается на процесс целиком, поэтому обновляем его перед задачей.
    usage = resource.getrusage(resource.RUSAGE_SELF)
    cpu_limit = math.ceil(usage.ru_utime + usage.ru_stime) + _WORKER_CPU_SECONDS
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit, resource.RLIM_INFINITY))
    try:
        template = (_rich_env if rich else env).from_string(template_str)
        chunks = []
        length = 0
        for chunk in template.generate(**context):
            length += len(chunk)
            if length > _MAX_RENDERED_LENGTH:
                raise ValueError("Слишком длинный результат шаблона")
            chunks.append(chunk)
        return "".join(chunks)
    except (MemoryError, OverflowError) as e:
        raise ValueError("Слишком длинный результат шаблона") from e


def _is_large_int(node: nodes.Node) -> bool:
    return (
        isinstance(node, nodes.Const)
        and isinstance(node.value, int)
        and not isinstance(node.value, bool)
        and node.value > _MAX_MULTIPLIER
    )


def _check_ast(node: nodes.Node) -> None:
    """
    Рекурсивно проверяет AST шаблона на недопустимые конструкции.

    Запрещены циклы, возведение в степень и умножение на большое целое:
    такие выражения способны надолго занять event loop или исчерпать память.
    """
    if isinstance(node, nodes.For):
        raise ValueError("Циклы запрещены в шаблонах")
    if isinstance(node, nodes.Pow):
        raise ValueError("Возведение в степень запрещено в шаблонах")
    if isinstance(node, nodes.Mul) and (_is_large_int(node.left) or _is_large_int(node.right)):
        raise ValueError("Слишком большой множитель в шаблоне")
    for child in node.iter_child_nodes():
        _check_ast(child)


def validate_template(template_str: str) -> None:
    """
    Валидирует шаблон: без циклов, возведения в степень и больших множителей.
    Вызывает ValueError при нарушении ограничений.
    """
    ast = env.parse(template_str)
    _check_ast(ast)


async def _render(template_str: str, context: dict[str, Any], *, rich: bool = False) -> str:
    """Рендерит в ограниченном процессе; при таймауте уничтожает пул."""
    pool = _get_render_pool()
    try:
        return await asyncio.wait_for(
            asyncio.wrap_future(pool.submit(_render_in_worker, template_str, context, rich)),
            timeout=_RENDER_TIMEOUT_SECONDS,
        )
    except (TimeoutError, BrokenProcessPool) as e:
        _reset_render_pool(pool)
        raise ValueError("Превышено время рендеринга шаблона") from e
    except asyncio.CancelledError:
        _reset_render_pool(pool)
        raise


async def render_template(template_str: str, context: dict[str, Any]) -> str:
    """
    Рендерит шаблон с предоставленным контекстом.
    Сначала валидирует шаблон, затем рендерит в отдельном процессе с таймаутом.
    Возвращает отрендеренную строку.
    """
    validate_template(template_str)
    return await _render(template_str, context)


async def render_rich_template(template_str: str, context: dict[str, Any]) -> str:
    """
    Рендерит rich-HTML шаблон с autoescape.

    Литеральные теги в шаблоне сохраняются нетронутыми, а подставляемые
    значения переменных HTML-экранируются автоматически (autoescape=True).

    Исключение: user.mention — намеренный HTML-линк; если передан как
    обычная строка, оборачивается в markupsafe.Markup автоматически.
    Фильтры bold/italic/code/mention тоже возвращают Markup — реальные теги
    сохраняются, но переданные в них значения экранируются внутри фильтра.

    Валидация ограничений выполняется через тот же _check_ast (используется
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
    _check_ast(ast)
    return await _render(template_str, ctx, rich=True)


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
        from app.core.time_util import get_timezone  # noqa: PLC0415

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
