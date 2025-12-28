from pathlib import Path

from fluent_compiler.bundle import FluentBundle
from fluentogram import FluentTranslator, TranslatorHub


def create_translator_hub() -> TranslatorHub:
    """Создает и настраивает хаб переводчиков."""
    locales_path = Path(__file__).parent.parent.parent / "locales"

    return TranslatorHub(
        {"ru": ("ru", "en"), "en": ("en", "ru")},
        [
            FluentTranslator(
                locale="ru",
                translator=FluentBundle.from_string(
                    "ru",
                    (locales_path / "ru" / "messages.ftl").read_text(encoding="utf-8"),
                ),
            ),
            FluentTranslator(
                locale="en",
                translator=FluentBundle.from_string(
                    "en",
                    (locales_path / "en" / "messages.ftl").read_text(encoding="utf-8"),
                ),
            ),
        ],
        root_locale="ru",
    )


translator_hub = create_translator_hub()
