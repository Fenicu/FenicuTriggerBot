"""Tests for find_matches in app/services/trigger_service.py."""

from types import SimpleNamespace


def _make_trigger(key_phrase: str, match_type: str, is_case_sensitive: bool = False):
    """Create a mock trigger object with the required attributes."""
    from app.db.models.trigger import MatchType

    return SimpleNamespace(
        key_phrase=key_phrase,
        match_type=MatchType(match_type),
        is_case_sensitive=is_case_sensitive,
    )


# ---------------------------------------------------------------------------
# EXACT matching
# ---------------------------------------------------------------------------


class TestFindMatchesExact:
    async def _fn(self, triggers, text):
        from app.services.trigger_service import find_matches

        return await find_matches(triggers, text)

    async def test_exact_match_case_insensitive(self):
        t = _make_trigger("Hello", "exact", is_case_sensitive=False)
        result = await self._fn([t], "hello")
        assert len(result) == 1

    async def test_exact_match_case_sensitive_hit(self):
        t = _make_trigger("Hello", "exact", is_case_sensitive=True)
        result = await self._fn([t], "Hello")
        assert len(result) == 1

    async def test_exact_match_case_sensitive_miss(self):
        t = _make_trigger("Hello", "exact", is_case_sensitive=True)
        result = await self._fn([t], "hello")
        assert len(result) == 0

    async def test_exact_no_match(self):
        t = _make_trigger("hello", "exact")
        result = await self._fn([t], "world")
        assert len(result) == 0

    async def test_exact_partial_text_no_match(self):
        t = _make_trigger("hello", "exact")
        result = await self._fn([t], "hello world")
        assert len(result) == 0


# ---------------------------------------------------------------------------
# CONTAINS matching
# ---------------------------------------------------------------------------


class TestFindMatchesContains:
    async def _fn(self, triggers, text):
        from app.services.trigger_service import find_matches

        return await find_matches(triggers, text)

    async def test_contains_match_case_insensitive(self):
        t = _make_trigger("World", "contains", is_case_sensitive=False)
        result = await self._fn([t], "hello world!")
        assert len(result) == 1

    async def test_contains_match_case_sensitive_hit(self):
        t = _make_trigger("World", "contains", is_case_sensitive=True)
        result = await self._fn([t], "hello World!")
        assert len(result) == 1

    async def test_contains_match_case_sensitive_miss(self):
        t = _make_trigger("World", "contains", is_case_sensitive=True)
        result = await self._fn([t], "hello world!")
        assert len(result) == 0

    async def test_contains_no_match(self):
        t = _make_trigger("xyz", "contains")
        result = await self._fn([t], "hello world")
        assert len(result) == 0

    async def test_contains_at_start(self):
        t = _make_trigger("hello", "contains")
        result = await self._fn([t], "hello world")
        assert len(result) == 1

    async def test_contains_at_end(self):
        t = _make_trigger("world", "contains")
        result = await self._fn([t], "hello world")
        assert len(result) == 1


# ---------------------------------------------------------------------------
# REGEXP matching
# ---------------------------------------------------------------------------


class TestFindMatchesRegexp:
    async def _fn(self, triggers, text):
        from app.services.trigger_service import find_matches

        return await find_matches(triggers, text)

    async def test_regexp_match(self):
        t = _make_trigger(r"\d{3}", "regexp")
        result = await self._fn([t], "code 123 here")
        assert len(result) == 1

    async def test_regexp_no_match(self):
        t = _make_trigger(r"^\d+$", "regexp")
        result = await self._fn([t], "abc")
        assert len(result) == 0

    async def test_regexp_invalid_pattern_skipped(self):
        t = _make_trigger(r"(unclosed", "regexp")
        result = await self._fn([t], "anything")
        assert len(result) == 0

    async def test_regexp_case_insensitive(self):
        t = _make_trigger(r"hello", "regexp", is_case_sensitive=False)
        result = await self._fn([t], "HELLO world")
        assert len(result) == 1

    async def test_regexp_case_sensitive_hit(self):
        t = _make_trigger(r"Hello", "regexp", is_case_sensitive=True)
        result = await self._fn([t], "Hello world")
        assert len(result) == 1

    async def test_regexp_case_sensitive_miss(self):
        t = _make_trigger(r"Hello", "regexp", is_case_sensitive=True)
        result = await self._fn([t], "hello world")
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Mixed / edge cases
# ---------------------------------------------------------------------------


class TestFindMatchesEdgeCases:
    async def _fn(self, triggers, text):
        from app.services.trigger_service import find_matches

        return await find_matches(triggers, text)

    async def test_mixed_types_multiple_matches(self):
        t1 = _make_trigger("hello", "exact")
        t2 = _make_trigger("hell", "contains")
        t3 = _make_trigger(r"h\w+o", "regexp")
        result = await self._fn([t1, t2, t3], "hello")
        assert len(result) == 3

    async def test_empty_triggers_list(self):
        result = await self._fn([], "hello world")
        assert len(result) == 0

    async def test_empty_text(self):
        t = _make_trigger("", "exact")
        result = await self._fn([t], "")
        assert len(result) == 1  # "" == ""

    async def test_empty_text_no_match_for_nonempty_key(self):
        t = _make_trigger("hello", "exact")
        result = await self._fn([t], "")
        assert len(result) == 0

    async def test_contains_empty_key_matches_anything(self):
        t = _make_trigger("", "contains")
        result = await self._fn([t], "any text")
        assert len(result) == 1  # "" in "any text" is True

    async def test_multiple_triggers_same_type(self):
        t1 = _make_trigger("hello", "contains")
        t2 = _make_trigger("world", "contains")
        result = await self._fn([t1, t2], "hello world")
        assert len(result) == 2

    async def test_only_matching_triggers_returned(self):
        t1 = _make_trigger("hello", "exact")
        t2 = _make_trigger("world", "exact")
        result = await self._fn([t1, t2], "hello")
        assert len(result) == 1
        assert result[0].key_phrase == "hello"
