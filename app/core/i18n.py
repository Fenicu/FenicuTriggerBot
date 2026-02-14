from datetime import datetime
from pathlib import Path
from typing import Any

from fluent_compiler.bundle import FluentBundle
from fluentogram import FluentTranslator, TranslatorHub

from app.core.time_util import format_dt

LOCALES_PATH = Path(__file__).parent.parent.parent / "locales"
ROOT_LOCALE = "ru"


def fluent_format_dt(dt: Any, format: str | None = None) -> str:
    if isinstance(dt, datetime):
        return format_dt(dt, format)
    return str(dt)


def _discover_locales() -> list[str]:
    """Обнаруживает доступные локали по наличию messages.ftl в директориях locales/."""
    return sorted(
        d.name
        for d in LOCALES_PATH.iterdir()
        if d.is_dir() and (d / "messages.ftl").exists()
    )


def _build_locales_map(locales: list[str]) -> dict[str, tuple[str, ...]]:
    """Строит карту фоллбэков: каждая локаль -> (она сама, root, остальные)."""
    locales_map = {}
    for locale in locales:
        if locale == ROOT_LOCALE:
            fallbacks = (locale, *(loc for loc in locales if loc != locale))
        else:
            fallbacks = (
                locale,
                ROOT_LOCALE,
                *(loc for loc in locales if loc not in (locale, ROOT_LOCALE)),
            )
        locales_map[locale] = fallbacks
    return locales_map


def create_translator_hub() -> TranslatorHub:
    """Создает и настраивает хаб переводчиков."""
    functions = {"DATETIME": fluent_format_dt}
    locales_map = _build_locales_map(available_locales)

    translators = [
        FluentTranslator(
            locale=locale,
            translator=FluentBundle.from_string(
                locale,
                (LOCALES_PATH / locale / "messages.ftl").read_text(encoding="utf-8"),
                functions=functions,
            ),
        )
        for locale in available_locales
    ]

    return TranslatorHub(locales_map, translators, root_locale=ROOT_LOCALE)


available_locales = _discover_locales()
translator_hub = create_translator_hub()
