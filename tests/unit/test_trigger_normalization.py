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
