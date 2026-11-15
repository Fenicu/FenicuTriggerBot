"""Матчинг regex-триггеров через пакет regex с реальным timeout."""

import time

from app.db.models.trigger import MatchType, Trigger
from app.services import trigger_service


def _trigger(trigger_id: int, pattern: str, *, case_sensitive: bool = False) -> Trigger:
    return Trigger(
        id=trigger_id,
        chat_id=-100,
        key_phrase=pattern,
        content={"text": "ok"},
        match_type=MatchType.REGEXP,
        is_case_sensitive=case_sensitive,
    )


async def test_catastrophic_pattern_returns_promptly_without_match():
    trigger = _trigger(1, r"(x+x+)+y")

    started = time.perf_counter()
    matches = await trigger_service.find_matches([trigger], "x" * 30)
    elapsed = time.perf_counter() - started

    assert matches == []
    assert elapsed < 2.0


async def test_normal_regex_still_matches_case_insensitive():
    trigger = _trigger(2, r"hello\d+")

    matches = await trigger_service.find_matches([trigger], "Say HELLO42 now")

    assert matches == [trigger]


async def test_regex_timeout_is_no_match_and_logged(monkeypatch, caplog):
    class _SlowPattern:
        def search(self, *_args, **_kwargs):
            raise TimeoutError

    monkeypatch.setattr(trigger_service.regex, "compile", lambda *_a, **_k: _SlowPattern())
    trigger = _trigger(7, r"(a+)+$")

    matches = await trigger_service.find_matches([trigger], "aaaa")

    assert matches == []
    assert "trigger 7" in caplog.text
