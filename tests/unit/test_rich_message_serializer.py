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


def _blocks_html(blocks, **kw):
    return rich_message_to_html(RichMessage.model_validate({"blocks": blocks}), **kw)


def test_block_paragraph_heading_divider_pre_footer():
    blocks = [
        {"type": "paragraph", "text": "p"},
        {"type": "heading", "text": "H", "size": 2},
        {"type": "heading", "text": "H9", "size": 9},   # clamp → h6
        {"type": "pre", "text": "code", "language": "py"},
        {"type": "footer", "text": "f"},
        {"type": "divider"},
    ]
    assert _blocks_html(blocks) == "<p>p</p><h2>H</h2><h6>H9</h6><pre>code</pre><footer>f</footer><hr>"


def test_block_list():
    blocks = [{"type": "list", "items": [
        {"label": "1", "blocks": [{"type": "paragraph", "text": "a"}]},
        {"label": "2", "blocks": [{"type": "paragraph", "text": "b"}]},
    ]}]
    assert _blocks_html(blocks) == "<ul><li><p>a</p></li><li><p>b</p></li></ul>"


def test_block_blockquote_with_credit():
    blocks = [{"type": "blockquote",
               "blocks": [{"type": "paragraph", "text": "q"}],
               "credit": "author"}]
    assert _blocks_html(blocks) == "<blockquote><p>q</p><footer>author</footer></blockquote>"


def test_block_details():
    blocks = [{"type": "details", "summary": "more",
               "blocks": [{"type": "paragraph", "text": "x"}]}]
    assert _blocks_html(blocks) == "<details><summary>more</summary><p>x</p></details>"


def test_block_table():
    blocks = [{"type": "table", "cells": [
        [{"align": "left", "valign": "top", "text": "H1", "is_header": True},
         {"align": "left", "valign": "top", "text": "H2", "is_header": True}],
        [{"align": "left", "valign": "top", "text": "a"},
         {"align": "left", "valign": "top", "text": "b"}],
    ]}]
    assert _blocks_html(blocks) == (
        '<table>'
        '<tr><th align="left" valign="top">H1</th><th align="left" valign="top">H2</th></tr>'
        '<tr><td align="left" valign="top">a</td><td align="left" valign="top">b</td></tr>'
        '</table>'
    )


def test_block_checklist():
    blocks = [{"type": "list", "items": [
        {"label": "x", "has_checkbox": True, "is_checked": True,
         "blocks": [{"type": "paragraph", "text": "done"}]},
        {"label": " ", "has_checkbox": True, "is_checked": False,
         "blocks": [{"type": "paragraph", "text": "todo"}]},
    ]}]
    assert _blocks_html(blocks) == (
        '<ul><li><input type="checkbox" checked><p>done</p></li>'
        '<li><input type="checkbox"><p>todo</p></li></ul>'
    )


def test_block_ordered_list():
    blocks = [{"type": "list", "items": [
        {"label": "1", "value": 1, "type": "1", "blocks": [{"type": "paragraph", "text": "a"}]},
        {"label": "2", "value": 2, "type": "1", "blocks": [{"type": "paragraph", "text": "b"}]},
    ]}]
    assert _blocks_html(blocks) == (
        '<ol type="1"><li value="1"><p>a</p></li><li value="2"><p>b</p></li></ol>'
    )


def test_block_table_full():
    blocks = [{"type": "table",
               "is_bordered": True, "is_striped": True,
               "caption": "Cap",
               "cells": [
                   [{"align": "center", "valign": "middle", "text": "H", "is_header": True, "colspan": 2}],
                   [{"align": "right", "valign": "bottom", "text": "x", "rowspan": 3}],
               ]}]
    assert _blocks_html(blocks) == (
        '<table bordered striped><caption>Cap</caption>'
        '<tr><th align="center" valign="middle" colspan="2">H</th></tr>'
        '<tr><td align="right" valign="bottom" rowspan="3">x</td></tr></table>'
    )


def test_block_math_and_thinking():
    blocks = [
        {"type": "mathematical_expression", "expression": "x^2"},
        {"type": "thinking", "text": "hmm"},
    ]
    assert _blocks_html(blocks) == "<tg-math-block>x^2</tg-math-block><blockquote><p>hmm</p></blockquote>"


def test_block_photo_with_base_url_and_caption():
    blocks = [{"type": "photo",
               "photo": [{"file_id": "small", "file_unique_id": "u1", "width": 90, "height": 90},
                         {"file_id": "big", "file_unique_id": "u2", "width": 800, "height": 600}],
               "caption": {"text": "cap"}}]
    out = _blocks_html(blocks, media_base_url="https://app.x/api/v1")
    assert out == '<img src="https://app.x/api/v1/media/proxy?file_id=big"><p>cap</p>'


def test_block_photo_without_base_url_keeps_caption_only():
    blocks = [{"type": "photo",
               "photo": [{"file_id": "big", "file_unique_id": "u", "width": 1, "height": 1}],
               "caption": {"text": "cap"}}]
    assert _blocks_html(blocks, media_base_url=None) == "<p>cap</p>"


def test_block_photo_empty_list_keeps_caption_only():
    # Пустой photo[] не должен ронять _largest_photo_id (max() по пустому);
    # поведение как при media_base_url=None — только caption, без <img>.
    blocks = [{"type": "photo", "photo": [], "caption": {"text": "c"}}]
    assert _blocks_html(blocks, media_base_url="https://a/api/v1") == "<p>c</p>"


def test_block_video_and_audio():
    blocks = [
        {"type": "video", "video": {"file_id": "v", "file_unique_id": "uv", "width": 1, "height": 1, "duration": 1}},
        {"type": "voice_note", "voice_note": {"file_id": "vc", "file_unique_id": "uc", "duration": 1}},
    ]
    out = _blocks_html(blocks, media_base_url="https://a/api/v1")
    assert out == ('<video src="https://a/api/v1/media/proxy?file_id=v"></video>'
                   '<audio src="https://a/api/v1/media/proxy?file_id=vc"></audio>')


def test_anchor_and_map_dropped():
    blocks = [{"type": "anchor", "name": "n"},
              {"type": "map", "location": {"latitude": 1.0, "longitude": 2.0},
               "zoom": 1, "width": 1, "height": 1}]
    assert _blocks_html(blocks) == ""
