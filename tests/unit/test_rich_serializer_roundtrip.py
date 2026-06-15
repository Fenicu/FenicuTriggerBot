# tests/unit/test_rich_serializer_roundtrip.py
from aiogram.types import RichMessage
from app.services.rich_html import rich_message_to_html, validate_rich_html


def test_complex_rich_message_roundtrips_through_validator():
    rm = RichMessage.model_validate({"blocks": [
        {"type": "heading", "text": "Заголовок", "size": 1},
        {"type": "paragraph", "text": [
            "Привет ", {"type": "bold", "text": "мир"}, " и ",
            {"type": "url", "text": "ссылка", "url": "https://e.com/?a=1&b=2"},
            " ", {"type": "spoiler", "text": "секрет"},
        ]},
        {"type": "list", "items": [
            {"label": "1", "blocks": [{"type": "paragraph", "text": "раз"}]},
            {"label": "2", "blocks": [{"type": "paragraph", "text": "два"}]},
        ]},
        {"type": "blockquote", "blocks": [{"type": "paragraph", "text": "цитата"}], "credit": "автор"},
        {"type": "table", "cells": [
            [{"align": "left", "valign": "top", "text": "A", "is_header": True}],
            [{"align": "left", "valign": "top", "text": "1"}],
        ]},
        {"type": "details", "summary": "детали", "blocks": [{"type": "paragraph", "text": "тело"}]},
        {"type": "mathematical_expression", "expression": "E=mc^2"},
        {"type": "divider"},
        {"type": "photo",
         "photo": [{"file_id": "big", "file_unique_id": "u", "width": 800, "height": 600}],
         "caption": {"text": "подпись"}},
    ]})
    html = rich_message_to_html(rm, media_base_url="https://app.example/api/v1")
    # не должно бросить RichHtmlError
    validate_rich_html(html)


def test_empty_blocks_roundtrips():
    rm = RichMessage.model_validate({"blocks": []})
    html = rich_message_to_html(rm)
    assert html == ""
    validate_rich_html(html)
