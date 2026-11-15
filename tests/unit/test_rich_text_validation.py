"""Регрессия aiogram 3.32: вложенный RichText валидируется без экспоненциального роста."""

import time

from aiogram.types import (
    Message,
    RichBlockParagraph,
    RichTextBold,
    RichTextItalic,
    RichTextSpoiler,
    RichTextStrikethrough,
    RichTextSubscript,
    RichTextUnderline,
)

_NESTING = [
    ("spoiler", RichTextSpoiler),
    ("bold", RichTextBold),
    ("subscript", RichTextSubscript),
    ("italic", RichTextItalic),
    ("underline", RichTextUnderline),
    ("strikethrough", RichTextStrikethrough),
]


def _nested_rich_message() -> dict:
    text: object = "deep"
    for kind, _ in reversed(_NESTING):
        text = {"type": kind, "text": text}
    return {
        "message_id": 1,
        "date": 1700000000,
        "chat": {"id": -100, "type": "supergroup"},
        "rich_message": {"blocks": [{"type": "paragraph", "text": text}]},
    }


def test_deeply_nested_rich_text_validates_fast_and_correctly():
    started = time.perf_counter()
    message = Message.model_validate(_nested_rich_message())
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0
    block = message.rich_message.blocks[0]
    assert isinstance(block, RichBlockParagraph)
    node = block.text
    for kind, cls in _NESTING:
        assert type(node) is cls
        assert node.type == kind
        node = node.text
    assert node == "deep"
