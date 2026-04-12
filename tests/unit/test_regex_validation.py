"""Tests for validate_regex in app/services/trigger_service.py."""

import asyncio
from unittest.mock import patch


# ---------------------------------------------------------------------------
# validate_regex
# ---------------------------------------------------------------------------


class TestValidateRegex:
    async def _fn(self, pattern: str) -> str | None:
        from app.services.trigger_service import validate_regex

        return await validate_regex(pattern)

    async def test_valid_simple_regex(self):
        result = await self._fn(r"hello")
        assert result is None

    async def test_valid_complex_regex(self):
        result = await self._fn(r"^(?:foo|bar)\d{2,4}$")
        assert result is None

    async def test_valid_character_class(self):
        result = await self._fn(r"[a-zA-Z0-9_]+")
        assert result is None

    async def test_invalid_syntax_unclosed_group(self):
        result = await self._fn(r"(abc")
        assert result is not None
        assert "Invalid regex" in result

    async def test_invalid_syntax_bad_quantifier(self):
        result = await self._fn(r"*abc")
        assert result is not None
        assert "Invalid regex" in result

    async def test_too_long_pattern(self):
        pattern = "a" * 501
        result = await self._fn(pattern)
        assert result is not None
        assert "too long" in result

    async def test_exactly_max_length_is_valid(self):
        pattern = "a" * 500
        result = await self._fn(pattern)
        assert result is None

    async def test_redos_pattern_detected_via_timeout(self):
        """Simulate ReDoS detection — mock asyncio.wait_for to raise TimeoutError.

        We cannot actually run a ReDoS pattern because the background thread
        with catastrophic backtracking is not interruptible in CPython.
        """
        from app.services.trigger_service import validate_regex

        original_wait_for = asyncio.wait_for

        async def mock_wait_for(coro, *, timeout=None):
            # Let re.compile succeed (it's fast), but make the probe stage timeout
            raise TimeoutError

        with patch("app.services.trigger_service.asyncio.wait_for", mock_wait_for):
            result = await validate_regex(r"(a+)+$")

        assert result is not None
        assert "too complex" in result.lower() or "ReDoS" in result

    async def test_empty_string_is_valid(self):
        result = await self._fn("")
        assert result is None

    async def test_special_characters(self):
        result = await self._fn(r"\.\*\+\?\[\]\(\)")
        assert result is None

    async def test_lookahead(self):
        result = await self._fn(r"(?=foo)bar")
        assert result is None

    async def test_lookbehind(self):
        result = await self._fn(r"(?<=foo)bar")
        assert result is None

    async def test_negative_lookahead(self):
        result = await self._fn(r"(?!foo)bar")
        assert result is None

    async def test_unicode_pattern(self):
        result = await self._fn(r"[а-яА-ЯёЁ]+")
        assert result is None

    async def test_alternation(self):
        result = await self._fn(r"cat|dog|fish")
        assert result is None

    async def test_valid_word_boundary(self):
        result = await self._fn(r"\bhello\b")
        assert result is None

    async def test_unclosed_bracket(self):
        result = await self._fn(r"[abc")
        assert result is not None
        assert "Invalid regex" in result
