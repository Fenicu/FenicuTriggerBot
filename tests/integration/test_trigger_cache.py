"""Кэш триггеров чата: порядок, состав полей, инвалидация."""

import json
import unicodedata
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import update

from app.db.models.trigger import AccessLevel, MatchType, ModerationStatus, Trigger
from app.services import trigger_service
from tests.factories import create_chat, create_trigger


async def test_get_triggers_by_chat_is_ordered_by_id(db_session):
    chat = await create_chat(db_session)
    first = await create_trigger(db_session, chat_id=chat.id, key_phrase="k1")
    second = await create_trigger(db_session, chat_id=chat.id, key_phrase="k2")
    third = await create_trigger(db_session, chat_id=chat.id, key_phrase="k3")
    await db_session.commit()
    # UPDATE переносит строку в конец кучи: без ORDER BY первый триггер вернулся бы последним
    await db_session.execute(update(Trigger).where(Trigger.id == first.id).values(key_phrase="k1 renamed"))
    await db_session.commit()

    triggers = await trigger_service.get_triggers_by_chat(db_session, chat.id)

    assert [t.id for t in triggers] == [first.id, second.id, third.id]


# ── состав кэша ──────────────────────────────────────────────────────────────

MATCH_FIELDS = {
    "id",
    "key_phrase",
    "match_type",
    "is_case_sensitive",
    "access_level",
    "is_template",
    "rich",
    "moderation_status",
}


@pytest.fixture
def real_valkey(valkey_client):
    with patch("app.services.trigger_service.valkey", valkey_client):
        yield valkey_client


def _cached_items(raw: str) -> list[dict]:
    payload = json.loads(raw)
    return payload["items"] if isinstance(payload, dict) else payload


async def test_cache_holds_only_matching_fields(db_session, real_valkey):
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="hi", content={"text": "x" * 5000})
    await db_session.commit()

    await trigger_service.get_triggers_by_chat(db_session, chat.id)

    raw = await real_valkey.get(f"triggers:{chat.id}")
    items = _cached_items(raw)
    assert len(items) == 1
    assert set(items[0]) == MATCH_FIELDS
    assert len(raw) < 500


async def test_cache_hit_returns_same_matching_data(db_session, real_valkey):
    chat = await create_chat(db_session)
    trigger = await create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="Admin Key",
        match_type=MatchType.CONTAINS,
        is_case_sensitive=True,
        access_level=AccessLevel.ADMINS,
        is_template=True,
        rich=True,
        moderation_status=ModerationStatus.PENDING,
    )
    await db_session.commit()

    from_db = await trigger_service.get_triggers_by_chat(db_session, chat.id)
    from_cache = await trigger_service.get_triggers_by_chat(db_session, chat.id)

    assert from_db == from_cache
    cached = from_cache[0]
    assert cached.id == trigger.id
    assert cached.key_phrase == "Admin Key"
    assert cached.match_type is MatchType.CONTAINS
    assert cached.is_case_sensitive is True
    assert cached.access_level is AccessLevel.ADMINS
    assert cached.is_template is True
    assert cached.rich is True
    assert cached.moderation_status is ModerationStatus.PENDING


async def test_cache_hit_does_not_query_database(db_session, real_valkey):
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="hi")
    await db_session.commit()
    await trigger_service.get_triggers_by_chat(db_session, chat.id)

    session = AsyncMock()
    triggers = await trigger_service.get_triggers_by_chat(session, chat.id)

    assert [t.key_phrase for t in triggers] == ["hi"]
    session.execute.assert_not_awaited()


async def test_legacy_cache_entry_with_content_is_still_readable(db_session, real_valkey):
    """Записи старого формата (полный список с content) доживают свой TTL после выката."""
    legacy = [
        {
            "id": 7,
            "chat_id": -1,
            "key_phrase": "old",
            "content": {"text": "body"},
            "match_type": "exact",
            "is_case_sensitive": False,
            "access_level": "all",
            "usage_count": 3,
            "created_by": 1,
            "is_template": False,
            "rich": False,
            "moderation_status": "safe",
        }
    ]
    await real_valkey.set("triggers:-1", json.dumps(legacy))

    triggers = await trigger_service.get_triggers_by_chat(AsyncMock(), -1)

    assert [(t.id, t.key_phrase, t.match_type) for t in triggers] == [(7, "old", MatchType.EXACT)]


async def test_get_trigger_content_returns_content(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id, content={"text": "body"})
    await db_session.commit()

    assert await trigger_service.get_trigger_content(db_session, trigger.id) == {"text": "body"}


async def test_get_trigger_content_is_none_for_deleted_or_missing(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id, is_deleted=True)
    await db_session.commit()

    assert await trigger_service.get_trigger_content(db_session, trigger.id) is None
    assert await trigger_service.get_trigger_content(db_session, 10**9) is None


async def test_find_matches_normalizes_message_text_once(monkeypatch):
    text = "ｈello ﬁne"
    triggers = [
        trigger_service.CachedTrigger(
            id=i,
            key_phrase=f"key{i}",
            match_type=match_type,
            is_case_sensitive=bool(i % 2),
            access_level=AccessLevel.ALL,
            is_template=False,
            rich=False,
            moderation_status=ModerationStatus.SAFE,
        )
        for i, match_type in enumerate([MatchType.EXACT] * 5 + [MatchType.CONTAINS] * 5 + [MatchType.REGEXP] * 2)
    ]
    real_normalize = unicodedata.normalize
    text_calls = 0

    def counting_normalize(form: str, value: str) -> str:
        nonlocal text_calls
        if value == text:
            text_calls += 1
        return real_normalize(form, value)

    monkeypatch.setattr(trigger_service.unicodedata, "normalize", counting_normalize)

    await trigger_service.find_matches(triggers, text)

    assert text_calls == 1


async def test_find_matches_on_cached_triggers_keeps_semantics():
    def make(i: int, key: str, match_type: MatchType, case_sensitive: bool = False) -> "trigger_service.CachedTrigger":
        return trigger_service.CachedTrigger(
            id=i,
            key_phrase=key,
            match_type=match_type,
            is_case_sensitive=case_sensitive,
            access_level=AccessLevel.ALL,
            is_template=False,
            rich=False,
            moderation_status=ModerationStatus.SAFE,
        )

    exact = make(1, "Straße", MatchType.EXACT)
    exact_cs = make(2, "STRASSE", MatchType.EXACT, case_sensitive=True)
    contains = make(3, "ｓｔｒ", MatchType.CONTAINS)
    contains_cs = make(4, "str", MatchType.CONTAINS, case_sensitive=True)
    regexp = make(5, r"^s.+e$", MatchType.REGEXP)

    matches = await trigger_service.find_matches([exact, exact_cs, contains, contains_cs, regexp], "STRASSE")

    assert matches == [regexp, exact, exact_cs, contains]
