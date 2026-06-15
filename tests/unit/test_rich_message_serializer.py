# tests/unit/test_rich_message_serializer.py
import pytest
from aiogram.types import RichMessage
from app.services.rich_html import rich_message_to_html


def _para(text):
    """Обернуть inline-узел в paragraph и вернуть RichMessage."""
    return RichMessage.model_validate({"blocks": [{"type": "paragraph", "text": text}]})


def _html(text):
    """Сериализовать одиночный paragraph и снять обёртку <p>…</p>."""
    out = rich_message_to_html(_para(text))
    assert out.startswith("<p>") and out.endswith("</p>")
    return out[3:-4]


@pytest.mark.parametrize(
    ("node", "expected"),
    [
        ("plain text", "plain text"),
        ("a & b < c > d", "a &amp; b &lt; c &gt; d"),
        ({"type": "bold", "text": "B"}, "<b>B</b>"),
        ({"type": "italic", "text": "I"}, "<i>I</i>"),
        ({"type": "underline", "text": "U"}, "<u>U</u>"),
        ({"type": "strikethrough", "text": "S"}, "<s>S</s>"),
        ({"type": "spoiler", "text": "X"}, "<tg-spoiler>X</tg-spoiler>"),
        ({"type": "code", "text": "c"}, "<code>c</code>"),
        ({"type": "marked", "text": "m"}, "<mark>m</mark>"),
        ({"type": "subscript", "text": "x"}, "<sub>x</sub>"),
        ({"type": "superscript", "text": "y"}, "<sup>y</sup>"),
        ({"type": "url", "text": "link", "url": "https://e.com/?a=1&b=2"},
         '<a href="https://e.com/?a=1&amp;b=2">link</a>'),
        ({"type": "custom_emoji", "custom_emoji_id": "555", "alternative_text": "🔥"},
         '<tg-emoji emoji-id="555">🔥</tg-emoji>'),
        ({"type": "mathematical_expression", "expression": "a<b"}, "<tg-math>a&lt;b</tg-math>"),
        ({"type": "anchor", "name": "sec1"}, ""),
        # auto-detect entities → plain inner
        ({"type": "hashtag", "text": "#tag", "hashtag": "tag"}, "#tag"),
        ({"type": "mention", "text": "@user", "username": "user"}, "@user"),
    ],
)
def test_inline_nodes(node, expected):
    assert _html(node) == expected


def test_inline_nested_list_and_wrappers():
    node = ["plain ", {"type": "bold", "text": ["b ", {"type": "italic", "text": "i"}]}]
    assert _html(node) == "plain <b>b <i>i</i></b>"


def test_inline_text_mention():
    node = {"type": "text_mention", "text": "Bob", "user": {"id": 42, "is_bot": False, "first_name": "Bob"}}
    assert _html(node) == '<a href="tg://user?id=42">Bob</a>'
