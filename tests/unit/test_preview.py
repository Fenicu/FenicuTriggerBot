"""Tests for app/services/preview_service.py — token generation, sanitization, rendering."""

from types import SimpleNamespace
from unittest.mock import patch


# ---------------------------------------------------------------------------
# generate_preview_token / verify_preview_token
# ---------------------------------------------------------------------------


class TestPreviewToken:
    def test_deterministic(self):
        from app.services.preview_service import generate_preview_token

        t1 = generate_preview_token(42)
        t2 = generate_preview_token(42)
        assert t1 == t2

    def test_different_ids_give_different_tokens(self):
        from app.services.preview_service import generate_preview_token

        t1 = generate_preview_token(1)
        t2 = generate_preview_token(2)
        assert t1 != t2

    def test_token_is_hex_string(self):
        from app.services.preview_service import generate_preview_token

        token = generate_preview_token(100)
        assert isinstance(token, str)
        # SHA256 hex digest is 64 chars
        assert len(token) == 64
        int(token, 16)  # Should not raise


class TestVerifyPreviewToken:
    def test_valid_token(self):
        from app.services.preview_service import generate_preview_token, verify_preview_token

        token = generate_preview_token(42)
        assert verify_preview_token(42, token) is True

    def test_invalid_token(self):
        from app.services.preview_service import verify_preview_token

        assert verify_preview_token(42, "definitely_wrong_token") is False

    def test_wrong_id(self):
        from app.services.preview_service import generate_preview_token, verify_preview_token

        token = generate_preview_token(42)
        assert verify_preview_token(43, token) is False

    def test_empty_token(self):
        from app.services.preview_service import verify_preview_token

        assert verify_preview_token(42, "") is False


# ---------------------------------------------------------------------------
# _sanitize_url
# ---------------------------------------------------------------------------


class TestSanitizeUrl:
    def _fn(self, url: str) -> str:
        from app.services.preview_service import _sanitize_url

        return _sanitize_url(url)

    def test_http_allowed(self):
        assert self._fn("http://example.com") == "http://example.com"

    def test_https_allowed(self):
        assert self._fn("https://example.com") == "https://example.com"

    def test_tg_protocol_allowed(self):
        assert self._fn("tg://user?id=123") == "tg://user?id=123"

    def test_javascript_blocked(self):
        assert self._fn("javascript:alert(1)") == "#"

    def test_data_protocol_blocked(self):
        assert self._fn("data:text/html,<h1>hi</h1>") == "#"

    def test_ftp_blocked(self):
        assert self._fn("ftp://files.example.com") == "#"

    def test_no_protocol_returns_hash(self):
        # No colon -> protocol is ""
        assert self._fn("example.com") == "#"

    def test_empty_string(self):
        assert self._fn("") == "#"


# ---------------------------------------------------------------------------
# _sanitize_html
# ---------------------------------------------------------------------------


class TestSanitizeHtml:
    def _fn(self, text: str) -> str:
        from app.services.preview_service import _sanitize_html

        return _sanitize_html(text)

    def test_safe_tags_pass_through(self):
        assert self._fn("<b>bold</b>") == "<b>bold</b>"
        assert self._fn("<i>italic</i>") == "<i>italic</i>"
        assert self._fn("<code>code</code>") == "<code>code</code>"

    def test_unsafe_tag_escaped(self):
        result = self._fn("<script>alert(1)</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_a_tag_keeps_href(self):
        result = self._fn('<a href="https://example.com">link</a>')
        assert 'href="https://example.com"' in result
        assert ">link</a>" in result

    def test_a_tag_strips_other_attributes(self):
        result = self._fn('<a href="https://ex.com" onclick="evil()" class="x">link</a>')
        assert "onclick" not in result
        assert "class" not in result
        assert 'href="https://ex.com"' in result

    def test_a_tag_javascript_href_blocked(self):
        result = self._fn('<a href="javascript:alert(1)">click</a>')
        assert 'href="#"' in result

    def test_safe_tag_attributes_stripped(self):
        result = self._fn('<b style="color:red" class="x">text</b>')
        assert result == "<b>text</b>"

    def test_tg_spoiler_allowed(self):
        result = self._fn("<tg-spoiler>hidden</tg-spoiler>")
        assert "<tg-spoiler>" in result

    def test_plain_text_unchanged(self):
        assert self._fn("hello world") == "hello world"

    def test_mixed_safe_and_unsafe(self):
        result = self._fn("<b>bold</b><script>bad</script><i>italic</i>")
        assert "<b>bold</b>" in result
        assert "&lt;script&gt;" in result
        assert "<i>italic</i>" in result

    def test_a_tag_without_href(self):
        result = self._fn("<a>no href</a>")
        assert "<a>" in result

    def test_nested_safe_tags(self):
        result = self._fn("<b><i>bold italic</i></b>")
        assert "<b><i>bold italic</i></b>" == result


# ---------------------------------------------------------------------------
# render_trigger_text
# ---------------------------------------------------------------------------


class TestRenderTriggerText:
    def _make_trigger(self, content):
        return SimpleNamespace(id=1, content=content)

    def test_text_content(self):
        from app.services.preview_service import render_trigger_text

        trigger = self._make_trigger(
            {
                "text": "Hello world",
                "message_id": 1,
                "date": 0,
                "chat": {"id": 0, "type": "private"},
            }
        )
        result = render_trigger_text(trigger)
        assert "Hello world" in result

    def test_empty_content_dict(self):
        from app.services.preview_service import render_trigger_text

        trigger = self._make_trigger({})
        result = render_trigger_text(trigger)
        assert result == ""

    def test_non_dict_content_returns_empty(self):
        from app.services.preview_service import render_trigger_text

        trigger = self._make_trigger("just a string")
        result = render_trigger_text(trigger)
        assert result == ""

    def test_none_content_returns_empty(self):
        from app.services.preview_service import render_trigger_text

        trigger = self._make_trigger(None)
        result = render_trigger_text(trigger)
        assert result == ""

    def test_caption_content(self):
        from app.services.preview_service import render_trigger_text

        trigger = self._make_trigger(
            {
                "caption": "My caption",
                "message_id": 1,
                "date": 0,
                "chat": {"id": 0, "type": "private"},
            }
        )
        result = render_trigger_text(trigger)
        assert "My caption" in result

    def test_fallback_to_text_field(self):
        """When Message deserialization fails, falls back to content['text']."""
        from app.services.preview_service import render_trigger_text

        # Deliberately malformed — not valid as a Message, but has 'text' key
        trigger = self._make_trigger({"text": "Fallback text"})
        result = render_trigger_text(trigger)
        # Either the Message parse works or falls back to html.escape(text)
        assert "Fallback" in result

    def test_content_with_only_photo(self):
        """Content with photo but no text/caption should return empty."""
        from app.services.preview_service import render_trigger_text

        trigger = self._make_trigger(
            {
                "photo": [{"file_id": "abc", "width": 100, "height": 100, "file_size": 1000}],
                "message_id": 1,
                "date": 0,
                "chat": {"id": 0, "type": "private"},
            }
        )
        result = render_trigger_text(trigger)
        assert result == ""
