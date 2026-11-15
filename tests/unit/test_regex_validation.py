"""Tests for validate_regex in app/services/trigger_service.py."""


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

    async def test_redos_pattern_detected_via_timeout(self, monkeypatch):
        """Pattern search, прерванный по timeout, отклоняется как ReDoS."""
        from app.services import trigger_service

        class _SlowPattern:
            def search(self, *_args, **_kwargs):
                raise TimeoutError

        monkeypatch.setattr(trigger_service.regex, "compile", lambda *_a, **_k: _SlowPattern())

        result = await trigger_service.validate_regex(r"(a+)+$")

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
