"""Unit-тесты на NFKC + casefold нормализацию ключей триггеров."""
import pytest

from app.services.trigger_service import _normalize_key, _normalize_for_match


def test_normalize_key_applies_nfkc_to_compatibility_form():
    """ﬁ (U+FB01) должно превратиться в fi."""
    assert _normalize_key("ﬁle") == "file"


def test_normalize_key_applies_nfkc_to_fullwidth():
    """Полноширинный Ｒ должен стать обычным R."""
    assert _normalize_key("Ｒ") == "R"


def test_normalize_key_idempotent_on_ascii():
    assert _normalize_key("hello") == "hello"


def test_normalize_key_idempotent_on_cyrillic():
    assert _normalize_key("привет") == "привет"


def test_normalize_for_match_lowercases_via_casefold():
    """casefold отличается от lower на немецкой sharp s."""
    assert _normalize_for_match("straße", case_sensitive=False) == "strasse"


def test_normalize_for_match_keeps_case_when_case_sensitive():
    assert _normalize_for_match("Привет", case_sensitive=True) == "Привет"


def test_normalize_for_match_applies_nfkc_before_casefold():
    """ﬁ + casefold → fi; FULLWIDTH R + casefold → r."""
    assert _normalize_for_match("ﬁle", case_sensitive=False) == "file"
    assert _normalize_for_match("Ｒ", case_sensitive=False) == "r"


import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from app.db.models.trigger import AccessLevel, MatchType, ModerationStatus, Trigger


@pytest.mark.asyncio
async def test_create_trigger_normalizes_key_to_nfkc():
    """create_trigger должен сохранять NFKC-нормализованный key_phrase."""
    from app.services.trigger_service import create_trigger

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()

    captured = {}

    def capture_add(trigger):
        captured["trigger"] = trigger

    session.add.side_effect = capture_add

    with (
        patch("app.services.trigger_service.add_history_step", new=AsyncMock()),
        patch("app.services.trigger_service.valkey") as vk,
    ):
        vk.delete = AsyncMock()
        await create_trigger(
            session=session,
            chat_id=-100,
            key_phrase="ﬁle",
            content={"text": "x"},
            match_type=MatchType.EXACT,
            skip_moderation=True,
        )

    assert captured["trigger"].key_phrase == "file"


@pytest.mark.asyncio
async def test_create_trigger_normalizes_regex_pattern_to_nfkc():
    """Для regex-режима паттерн тоже нормализуется."""
    from app.services.trigger_service import create_trigger

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()

    captured = {}
    session.add.side_effect = lambda t: captured.update(trigger=t)

    with (
        patch("app.services.trigger_service.add_history_step", new=AsyncMock()),
        patch("app.services.trigger_service.valkey") as vk,
    ):
        vk.delete = AsyncMock()
        await create_trigger(
            session=session,
            chat_id=-100,
            key_phrase="Ｒ.*",
            content={"text": "x"},
            match_type=MatchType.REGEXP,
            skip_moderation=True,
        )

    assert captured["trigger"].key_phrase == "R.*"
