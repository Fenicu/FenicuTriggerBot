"""Тесты временного патча aiogram 3.31.0: линейная валидация вложенного RichText."""

import time

import pytest
from aiogram.types import (
    Message,
    RichBlockParagraph,
    RichTextBold,
    RichTextItalic,
    RichTextSpoiler,
    RichTextStrikethrough,
    RichTextSubscript,
    RichTextUnderline,
    base,
)
from app.core import aiogram_patch
from app.core.aiogram_patch import patch_aiogram

# Без патча каждый уровень умножает время примерно в 20 раз: 5 уровней -- секунды,
# 6 -- минуты. С патчем это миллисекунды.
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
    patch_aiogram()

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


def test_patch_keeps_unset_removal():
    patch_aiogram()

    message = Message.model_validate({**_nested_rich_message(), "text": base.UNSET})

    assert message.text is None


def test_patch_is_idempotent():
    patch_aiogram()
    func = base.TelegramObject.remove_unset.__func__
    code = func.__code__

    patch_aiogram()

    assert func.__code__ is code
    assert Message.model_validate(_nested_rich_message()).rich_message is not None


def test_patch_exits_on_unexpected_aiogram_version(monkeypatch):
    monkeypatch.setattr(aiogram_patch, "version", lambda _: "3.32.0")

    with pytest.raises(SystemExit) as exc_info:
        patch_aiogram()

    assert exc_info.value.code == 1
