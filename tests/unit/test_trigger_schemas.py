"""Тесты схем TriggerCreate и TriggerUpdate."""

import pytest
from pydantic import ValidationError

from app.db.models.trigger import AccessLevel, MatchType
from app.schemas.trigger import TriggerCreate, TriggerUpdate


class TestTriggerCreate:
    def test_minimal_defaults(self):
        t = TriggerCreate(chat_id=1, key_phrase="hi", content={"text": "<b>x</b>"})
        assert t.rich is False
        assert t.is_template is False
        assert t.match_type == MatchType.EXACT
        assert t.is_case_sensitive is False
        assert t.access_level == AccessLevel.ALL

    def test_empty_key_phrase_rejected(self):
        with pytest.raises(ValidationError):
            TriggerCreate(chat_id=1, key_phrase="", content={"text": "x"})

    def test_key_phrase_too_long_rejected(self):
        with pytest.raises(ValidationError):
            TriggerCreate(chat_id=1, key_phrase="x" * 256, content={"text": "x"})

    def test_all_fields(self):
        t = TriggerCreate(
            chat_id=42,
            key_phrase="test phrase",
            content={"text": "hello"},
            match_type=MatchType.REGEXP,
            is_case_sensitive=True,
            access_level=AccessLevel.ADMINS,
            is_template=True,
            rich=True,
        )
        assert t.chat_id == 42
        assert t.match_type == MatchType.REGEXP
        assert t.rich is True
        assert t.is_template is True


class TestTriggerUpdate:
    def test_empty_update_allowed(self):
        t = TriggerUpdate()
        assert t.key_phrase is None
        assert t.content is None
        assert t.match_type is None

    def test_partial_update(self):
        t = TriggerUpdate(key_phrase="new phrase", rich=True)
        assert t.key_phrase == "new phrase"
        assert t.rich is True
        assert t.content is None

    def test_all_fields_optional(self):
        t = TriggerUpdate(
            key_phrase="kp",
            content={"text": "x"},
            match_type=MatchType.CONTAINS,
            is_case_sensitive=True,
            access_level=AccessLevel.OWNER,
            is_template=False,
            rich=False,
        )
        assert t.match_type == MatchType.CONTAINS
        assert t.access_level == AccessLevel.OWNER
