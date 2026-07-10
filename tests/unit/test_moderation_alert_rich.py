"""Tests for build_alert_rich_html — rich-HTML moderation alert builder."""

from app.bot.handlers.moderation import build_alert_rich_html
from app.services.rich_html import validate_rich_html


def test_build_alert_rich_html_escapes_hostile_content():
    """Опасный контент должен экранироваться и проходить validate_rich_html."""
    html = build_alert_rich_html(
        category="Scam",
        confidence=0.91,
        chat_id=-1001234567890,
        trigger_id=777,
        trigger_key='<b>x</b>&"',
        content_type="text",
        content_text="a < b > c & d",
        reasoning="a<script>alert(1)</script> & <b>",
    )

    validate_rich_html(html)

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;b&gt;x&lt;/b&gt;" in html


def test_build_alert_rich_html_empty_fields_use_dash():
    """Пустые content_text/reasoning заменяются на '—'."""
    html = build_alert_rich_html(
        category="Safe",
        confidence="N/A",
        chat_id=42,
        trigger_id=1,
        trigger_key="hello",
        content_type="photo",
        content_text="",
        reasoning=None,
    )

    validate_rich_html(html)
    assert "<details><summary>📄 Содержание</summary><p>—</p></details>" in html
    assert "<details><summary>🧠 Заключение модели</summary><p>—</p></details>" in html


def test_build_alert_rich_html_truncates_long_fields():
    """content_text/reasoning длиннее 3000 символов обрезаются с многоточием."""
    html = build_alert_rich_html(
        category="Scam",
        confidence=0.5,
        chat_id=42,
        trigger_id=1,
        trigger_key="key",
        content_type="text",
        content_text="x" * 5000,
        reasoning="y" * 5000,
    )

    validate_rich_html(html)
    assert "x" * 3000 + "…" in html
    assert "y" * 3000 + "…" in html
    assert "x" * 3001 not in html


def test_build_alert_rich_html_includes_transcript_block():
    """Непустой transcript даёт блок «Распознанная речь» с текстом."""
    html = build_alert_rich_html(
        category="Scam",
        confidence=0.8,
        chat_id=1,
        trigger_id=2,
        trigger_key="key",
        content_type="voice",
        content_text=None,
        reasoning="ok",
        transcript="купи закладку",
    )

    validate_rich_html(html)
    assert "Распознанная речь" in html
    assert "купи закладку" in html


def test_build_alert_rich_html_omits_transcript_block_when_empty():
    """Пустой/None transcript — блока «Распознанная речь» нет вовсе."""
    for empty_transcript in (None, ""):
        html = build_alert_rich_html(
            category="Safe",
            confidence="N/A",
            chat_id=1,
            trigger_id=2,
            trigger_key="key",
            content_type="text",
            content_text="hi",
            reasoning="ok",
            transcript=empty_transcript,
        )

        validate_rich_html(html)
        assert "Распознанная речь" not in html
        assert "<details><summary>🎤" not in html
