from datetime import datetime
from pathlib import Path
from typing import Any

from fluent_compiler.bundle import FluentBundle
from fluentogram import FluentTranslator, TranslatorHub

from app.core.time_util import format_dt


def fluent_format_dt(dt: Any, format: str | None = None) -> str:
    if isinstance(dt, datetime):
        return format_dt(dt, format)
    return str(dt)


def create_translator_hub() -> TranslatorHub:
    """Создает и настраивает хаб переводчиков."""
    locales_path = Path(__file__).parent.parent.parent / "locales"
    functions = {"DATETIME": fluent_format_dt}

    return TranslatorHub(
        {"ru": ("ru", "en"), "en": ("en", "ru")},
        [
            FluentTranslator(
                locale="ru",
                translator=FluentBundle.from_string(
                    "ru",
                    (locales_path / "ru" / "messages.ftl").read_text(encoding="utf-8"),
                    functions=functions,
                ),
            ),
            FluentTranslator(
                locale="en",
                translator=FluentBundle.from_string(
                    "en",
                    (locales_path / "en" / "messages.ftl").read_text(encoding="utf-8"),
                    functions=functions,
                ),
            ),
        ],
        root_locale="ru",
    )


translator_hub = create_translator_hub()
