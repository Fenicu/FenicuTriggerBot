"""Юниты на чистые хелперы из creation_private."""
import pytest

from app.bot.handlers.creation_private import parse_deep_link


def test_parse_deep_link_returns_chat_id_for_valid_supergroup():
    assert parse_deep_link("newtrigger_-1001234567890") == -1001234567890


def test_parse_deep_link_returns_chat_id_for_positive_id():
    """Личные/legacy-чаты имеют положительный id — поддерживаем тоже."""
    assert parse_deep_link("newtrigger_42") == 42


def test_parse_deep_link_returns_none_for_none():
    assert parse_deep_link(None) is None


def test_parse_deep_link_returns_none_for_empty():
    assert parse_deep_link("") is None


def test_parse_deep_link_returns_none_for_unknown_prefix():
    assert parse_deep_link("captcha_123") is None
    assert parse_deep_link("settings_-100") is None


def test_parse_deep_link_returns_none_for_non_numeric_suffix():
    assert parse_deep_link("newtrigger_abc") is None


def test_parse_deep_link_returns_none_for_bare_prefix():
    assert parse_deep_link("newtrigger_") is None
