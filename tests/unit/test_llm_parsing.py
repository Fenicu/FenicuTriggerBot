"""Tests for app/worker/llm.py — pure parsing/validation functions."""

import base64
import json


# ---------------------------------------------------------------------------
# _extract_json_object
# ---------------------------------------------------------------------------


class TestExtractJsonObject:
    def _fn(self, text: str) -> str | None:
        from app.worker.llm import _extract_json_object

        return _extract_json_object(text)

    def test_simple_json(self):
        raw = '{"category": "Safe", "confidence": 0.9, "reasoning": "ok"}'
        assert self._fn(raw) == raw

    def test_json_with_leading_text(self):
        raw = 'Here is the result: {"category": "Safe"} done'
        assert self._fn(raw) == '{"category": "Safe"}'

    def test_braces_inside_strings(self):
        raw = '{"reasoning": "found {bad} content", "category": "Drugs"}'
        result = self._fn(raw)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["reasoning"] == "found {bad} content"

    def test_nested_objects(self):
        raw = '{"outer": {"inner": 1}, "val": 2}'
        result = self._fn(raw)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["outer"]["inner"] == 1
        assert parsed["val"] == 2

    def test_no_json_returns_none(self):
        assert self._fn("no json here at all") is None

    def test_empty_string_returns_none(self):
        assert self._fn("") is None

    def test_malformed_json_unclosed_brace(self):
        raw = '{"category": "Safe"'
        assert self._fn(raw) is None

    def test_markdown_wrapped_json(self):
        raw = '```json\n{"category": "Safe", "confidence": 0.8}\n```'
        result = self._fn(raw)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["category"] == "Safe"

    def test_escaped_quotes_in_string(self):
        raw = r'{"reasoning": "he said \"hello\"", "category": "Safe"}'
        result = self._fn(raw)
        assert result is not None
        parsed = json.loads(result)
        assert "hello" in parsed["reasoning"]

    def test_multiple_json_objects_returns_first(self):
        raw = '{"a": 1} {"b": 2}'
        result = self._fn(raw)
        assert result is not None
        parsed = json.loads(result)
        assert parsed == {"a": 1}


# ---------------------------------------------------------------------------
# _validate_result
# ---------------------------------------------------------------------------


class TestValidateResult:
    def _fn(self, data: dict):
        from app.worker.llm import _validate_result

        return _validate_result(data)

    def test_valid_safe_category(self):
        result = self._fn({"category": "Safe", "confidence": 0.95, "reasoning": "ok"})
        assert result is not None
        assert result.category == "Safe"
        assert result.confidence == 0.95
        assert result.reasoning == "ok"

    def test_valid_drugs_category(self):
        result = self._fn({"category": "Drugs", "confidence": 0.8, "reasoning": "found drugs"})
        assert result is not None
        assert result.category == "Drugs"

    def test_all_valid_categories(self):
        for cat in ("Drugs", "Porn", "Scam", "Violence", "PersonalData", "Safe"):
            result = self._fn({"category": cat, "confidence": 0.5, "reasoning": ""})
            assert result is not None, f"Category '{cat}' should be valid"

    def test_invalid_category_returns_none(self):
        result = self._fn({"category": "Unknown", "confidence": 0.5, "reasoning": "hmm"})
        assert result is None

    def test_missing_category_returns_none(self):
        result = self._fn({"confidence": 0.5, "reasoning": "no cat"})
        assert result is None

    def test_confidence_clamped_above_one(self):
        result = self._fn({"category": "Safe", "confidence": 1.5, "reasoning": ""})
        assert result is not None
        assert result.confidence == 1.0

    def test_confidence_clamped_below_zero(self):
        result = self._fn({"category": "Safe", "confidence": -0.3, "reasoning": ""})
        assert result is not None
        assert result.confidence == 0.0

    def test_non_numeric_confidence_defaults(self):
        result = self._fn({"category": "Safe", "confidence": "high", "reasoning": ""})
        assert result is not None
        assert result.confidence == 0.5

    def test_missing_confidence_defaults(self):
        result = self._fn({"category": "Safe", "reasoning": "ok"})
        assert result is not None
        assert result.confidence == 0.5

    def test_missing_reasoning_defaults_to_empty(self):
        result = self._fn({"category": "Safe", "confidence": 0.9})
        assert result is not None
        assert result.reasoning == ""

    def test_integer_confidence(self):
        result = self._fn({"category": "Safe", "confidence": 1, "reasoning": ""})
        assert result is not None
        assert result.confidence == 1.0


# ---------------------------------------------------------------------------
# _parse_result
# ---------------------------------------------------------------------------


class TestParseResult:
    def _fn(self, content: str):
        from app.worker.llm import _parse_result

        return _parse_result(content)

    def test_full_valid_json_response(self):
        content = '{"category": "Safe", "confidence": 0.85, "reasoning": "Normal text"}'
        result = self._fn(content)
        assert result is not None
        assert result.category == "Safe"
        assert result.confidence == 0.85

    def test_json_in_markdown_code_block(self):
        content = '```json\n{"category": "Drugs", "confidence": 0.9, "reasoning": "found drugs"}\n```'
        result = self._fn(content)
        assert result is not None
        assert result.category == "Drugs"

    def test_reasoning_with_braces(self):
        content = '{"category": "Safe", "confidence": 0.7, "reasoning": "text contains {braces} and {more}"}'
        result = self._fn(content)
        assert result is not None
        assert result.category == "Safe"
        assert "{braces}" in result.reasoning

    def test_empty_response_returns_none(self):
        result = self._fn("")
        assert result is None

    def test_garbage_input_returns_none(self):
        result = self._fn("this is total garbage with no json whatsoever")
        assert result is None

    def test_json_with_leading_reasoning_text(self):
        content = (
            "I think this is safe because it is just a greeting.\n\n"
            '{"category": "Safe", "confidence": 0.95, "reasoning": "Just a greeting"}'
        )
        result = self._fn(content)
        assert result is not None
        assert result.category == "Safe"

    def test_invalid_category_in_valid_json(self):
        content = '{"category": "Spam", "confidence": 0.5, "reasoning": "spam content"}'
        result = self._fn(content)
        assert result is None

    def test_json_with_whitespace(self):
        content = '  \n  {"category": "Safe", "confidence": 0.8, "reasoning": "ok"}  \n  '
        result = self._fn(content)
        assert result is not None
        assert result.category == "Safe"

    def test_broken_json_returns_none(self):
        content = '{"category": "Safe", "confidence": }'
        result = self._fn(content)
        assert result is None


# ---------------------------------------------------------------------------
# _build_user_content
# ---------------------------------------------------------------------------


class TestBuildUserContent:
    def _fn(self, text: str, caption: str, image: bytes | None) -> list[dict]:
        from app.worker.llm import _build_user_content

        return _build_user_content(text, caption, image)

    def test_text_only(self):
        parts = self._fn("hello world", "", None)
        assert len(parts) == 1
        assert parts[0]["type"] == "text"
        assert "Text: hello world" in parts[0]["text"]

    def test_text_and_caption(self):
        parts = self._fn("hello", "my caption", None)
        assert len(parts) == 1
        text = parts[0]["text"]
        assert "Text: hello" in text
        assert "Caption: my caption" in text

    def test_image_with_text(self):
        img = b"\x89PNG\r\n\x1a\nfakedata"
        parts = self._fn("some text", "", img)
        assert len(parts) == 2
        assert parts[0]["type"] == "image_url"
        b64 = base64.b64encode(img).decode()
        assert b64 in parts[0]["image_url"]["url"]
        assert parts[1]["type"] == "text"
        assert "Text: some text" in parts[1]["text"]

    def test_image_only_no_text_no_caption(self):
        img = b"fakeimage"
        parts = self._fn("", "", img)
        assert len(parts) == 2
        assert parts[0]["type"] == "image_url"
        assert parts[1]["type"] == "text"
        assert "Classify this trigger content." in parts[1]["text"]
        # Should NOT have "Text:" or "Caption:" lines
        assert "Text:" not in parts[1]["text"]
        assert "Caption:" not in parts[1]["text"]

    def test_no_content_at_all(self):
        parts = self._fn("", "", None)
        assert len(parts) == 1
        assert parts[0]["type"] == "text"
        assert "Classify this trigger content." in parts[0]["text"]

    def test_caption_only(self):
        parts = self._fn("", "only caption", None)
        assert len(parts) == 1
        text = parts[0]["text"]
        assert "Caption: only caption" in text
        assert "Text:" not in text

    def test_image_base64_encoding(self):
        img = b"\x00\x01\x02\x03"
        parts = self._fn("", "", img)
        expected_b64 = base64.b64encode(img).decode()
        assert f"data:image/jpeg;base64,{expected_b64}" == parts[0]["image_url"]["url"]


# ---------------------------------------------------------------------------
# is_username_only
# ---------------------------------------------------------------------------


class TestIsUsernameOnly:
    def _fn(self, text: str) -> bool:
        from app.worker.llm import is_username_only

        return is_username_only(text)

    def test_bare_username(self):
        assert self._fn("@smertyyk") is True

    def test_username_with_surrounding_whitespace(self):
        assert self._fn("  @smertyyk  \n") is True

    def test_min_length_username(self):
        assert self._fn("@abcde") is True  # 5 chars минимум

    def test_max_length_username(self):
        assert self._fn("@" + "a" * 32) is True

    def test_too_short_rejected(self):
        assert self._fn("@abcd") is False  # 4 chars

    def test_too_long_rejected(self):
        assert self._fn("@" + "a" * 33) is False

    def test_without_at_sign_rejected(self):
        assert self._fn("smertyyk") is False

    def test_starts_with_digit_rejected(self):
        assert self._fn("@1smert") is False

    def test_starts_with_underscore_rejected(self):
        assert self._fn("@_smert") is False

    def test_two_usernames_rejected(self):
        assert self._fn("@one @two") is False

    def test_username_with_text_rejected(self):
        assert self._fn("@smertyyk привет") is False

    def test_username_with_url_rejected(self):
        assert self._fn("@smertyyk https://example.com") is False

    def test_empty_string_rejected(self):
        assert self._fn("") is False

    def test_only_whitespace_rejected(self):
        assert self._fn("   \n  ") is False

    def test_invalid_chars_rejected(self):
        assert self._fn("@smert-yyk") is False
        assert self._fn("@smert.yyk") is False

    def test_cyrillic_rejected(self):
        assert self._fn("@смертук") is False
