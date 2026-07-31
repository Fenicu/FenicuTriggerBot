"""Integration tests for app/services/trigger_service.py."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.db.models.daily_stat import DailyStat
from app.db.models.moderation_history import ModerationHistory, ModerationStep
from app.db.models.trigger import AccessLevel, MatchType, ModerationStatus, Trigger
from app.services import trigger_service
from tests.factories import create_banned_chat, create_chat, create_trigger, create_user


# ── create_trigger ───────────────────────────────────────────────────────────


async def test_create_trigger_basic(db_session):
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    await db_session.commit()

    trigger = await trigger_service.create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="hello",
        content={"text": "Hello!"},
        created_by=user.id,
        skip_moderation=True,
    )

    assert trigger.id is not None
    assert trigger.chat_id == chat.id
    assert trigger.key_phrase == "hello"
    assert trigger.content == {"text": "Hello!"}
    assert trigger.moderation_status == ModerationStatus.SAFE
    assert trigger.created_by == user.id
    assert trigger.is_deleted is False


async def test_create_trigger_skip_moderation_sets_safe(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    trigger = await trigger_service.create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="hi",
        content={"text": "Hi!"},
        created_by=None,
        skip_moderation=True,
    )

    assert trigger.moderation_status == ModerationStatus.SAFE


async def test_create_trigger_with_moderation_sets_pending(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    trigger = await trigger_service.create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="test_mod",
        content={"text": "Some content"},
        created_by=None,
        skip_moderation=False,
    )

    assert trigger.moderation_status == ModerationStatus.PENDING


async def test_create_trigger_with_buttons(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    content = {
        "text": "Click below",
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "Google", "url": "https://google.com"}],
                [{"text": "Help", "url": "https://help.com"}],
            ]
        },
    }
    trigger = await trigger_service.create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="buttons_test",
        content=content,
        created_by=None,
        skip_moderation=False,
    )

    assert trigger.id is not None
    assert trigger.content["reply_markup"]["inline_keyboard"] is not None


async def test_create_trigger_with_file_content(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    content = {
        "photo": [
            {"file_id": "small_id", "width": 100, "height": 100},
            {"file_id": "large_id", "width": 800, "height": 600},
        ],
        "caption": "A photo",
    }
    trigger = await trigger_service.create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="photo_trigger",
        content=content,
        created_by=None,
        skip_moderation=False,
    )

    assert trigger.id is not None
    assert trigger.content["photo"][1]["file_id"] == "large_id"


async def test_create_trigger_adds_history_step(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    trigger = await trigger_service.create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="hist",
        content={"text": "Test"},
        created_by=None,
        skip_moderation=True,
    )

    stmt = select(ModerationHistory).where(ModerationHistory.trigger_id == trigger.id)
    result = await db_session.execute(stmt)
    history = result.scalars().all()

    assert len(history) >= 1
    assert history[0].step == ModerationStep.CREATED.value


async def test_create_trigger_with_match_type_contains(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    trigger = await trigger_service.create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="partial",
        content={"text": "Found!"},
        match_type=MatchType.CONTAINS,
        created_by=None,
        skip_moderation=True,
    )

    assert trigger.match_type == MatchType.CONTAINS


# ── get_trigger_by_id ────────────────────────────────────────────────────────


async def test_get_trigger_by_id_existing(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id)
    await db_session.commit()

    found = await trigger_service.get_trigger_by_id(db_session, trigger.id)
    assert found is not None
    assert found.id == trigger.id


async def test_get_trigger_by_id_nonexistent(db_session):
    found = await trigger_service.get_trigger_by_id(db_session, 999999)
    assert found is None


async def test_get_trigger_by_id_soft_deleted_returns_none(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id, is_deleted=True, deleted_at=datetime.now(timezone.utc))
    await db_session.commit()

    found = await trigger_service.get_trigger_by_id(db_session, trigger.id)
    assert found is None


# ── get_trigger_by_key ───────────────────────────────────────────────────────


async def test_get_trigger_by_key_existing(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id, key_phrase="my_key")
    await db_session.commit()

    found = await trigger_service.get_trigger_by_key(db_session, chat.id, "my_key")
    assert found is not None
    assert found.key_phrase == "my_key"


async def test_get_trigger_by_key_nonexistent(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    found = await trigger_service.get_trigger_by_key(db_session, chat.id, "nope")
    assert found is None


async def test_get_trigger_by_key_soft_deleted(db_session):
    chat = await create_chat(db_session)
    await create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="del_key",
        is_deleted=True,
        deleted_at=datetime.now(timezone.utc),
    )
    await db_session.commit()

    found = await trigger_service.get_trigger_by_key(db_session, chat.id, "del_key")
    assert found is None


# ── get_triggers_by_chat ─────────────────────────────────────────────────────


async def test_get_triggers_by_chat_multiple(db_session):
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="t1")
    await create_trigger(db_session, chat_id=chat.id, key_phrase="t2")
    await create_trigger(db_session, chat_id=chat.id, key_phrase="t3")
    await db_session.commit()

    triggers = await trigger_service.get_triggers_by_chat(db_session, chat.id)
    assert len(triggers) == 3


async def test_get_triggers_by_chat_excludes_soft_deleted(db_session):
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="alive")
    await create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="dead",
        is_deleted=True,
        deleted_at=datetime.now(timezone.utc),
    )
    await db_session.commit()

    triggers = await trigger_service.get_triggers_by_chat(db_session, chat.id)
    assert len(triggers) == 1
    assert triggers[0].key_phrase == "alive"


async def test_get_triggers_by_chat_caches_to_valkey(db_session):
    from unittest.mock import AsyncMock
    from app.core.valkey import valkey

    chat = await create_chat(db_session)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="cached")
    await db_session.commit()

    # valkey.get returns None (cache miss) by default via autouse mock
    await trigger_service.get_triggers_by_chat(db_session, chat.id)

    valkey.set.assert_called()
    call_args = valkey.set.call_args
    assert f"triggers:{chat.id}" in call_args[0] or f"triggers:{chat.id}" == call_args[0][0]


async def test_get_triggers_by_chat_empty(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    triggers = await trigger_service.get_triggers_by_chat(db_session, chat.id)
    assert triggers == []


# ── delete_trigger_by_id ─────────────────────────────────────────────────────


async def test_delete_trigger_by_id_soft_deletes(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id)
    await db_session.commit()

    result = await trigger_service.delete_trigger_by_id(db_session, trigger.id)
    assert result is True

    await db_session.refresh(trigger)
    assert trigger.is_deleted is True
    assert trigger.deleted_at is not None


async def test_delete_trigger_by_id_already_deleted(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(
        db_session,
        chat_id=chat.id,
        is_deleted=True,
        deleted_at=datetime.now(timezone.utc),
    )
    await db_session.commit()

    result = await trigger_service.delete_trigger_by_id(db_session, trigger.id)
    assert result is False


async def test_delete_trigger_by_id_nonexistent(db_session):
    result = await trigger_service.delete_trigger_by_id(db_session, 999999)
    assert result is False


# ── delete_trigger_by_key ────────────────────────────────────────────────────


async def test_delete_trigger_by_key_soft_deletes(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id, key_phrase="to_delete")
    await db_session.commit()

    result = await trigger_service.delete_trigger_by_key(db_session, chat.id, "to_delete")
    assert result is True

    await db_session.refresh(trigger)
    assert trigger.is_deleted is True
    assert trigger.deleted_at is not None


async def test_delete_trigger_by_key_nonexistent(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    result = await trigger_service.delete_trigger_by_key(db_session, chat.id, "no_such_key")
    assert result is False


# ── delete_all_triggers_by_chat ──────────────────────────────────────────────


async def test_delete_all_triggers_by_chat(db_session):
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="a1")
    await create_trigger(db_session, chat_id=chat.id, key_phrase="a2")
    await create_trigger(db_session, chat_id=chat.id, key_phrase="a3")
    await db_session.commit()

    count = await trigger_service.delete_all_triggers_by_chat(db_session, chat.id)
    assert count == 3

    # All should be soft-deleted now
    stmt = select(Trigger).where(Trigger.chat_id == chat.id, Trigger.is_deleted.is_(False))
    result = await db_session.execute(stmt)
    assert len(result.scalars().all()) == 0


async def test_delete_all_triggers_empty_chat(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    count = await trigger_service.delete_all_triggers_by_chat(db_session, chat.id)
    assert count == 0


# ── get_triggers_count ───────────────────────────────────────────────────────


async def test_get_triggers_count_excludes_deleted(db_session):
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="c1")
    await create_trigger(db_session, chat_id=chat.id, key_phrase="c2")
    await create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="c3_del",
        is_deleted=True,
        deleted_at=datetime.now(timezone.utc),
    )
    await db_session.commit()

    count = await trigger_service.get_triggers_count(db_session, chat.id)
    assert count == 2


async def test_get_triggers_count_empty_chat(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    count = await trigger_service.get_triggers_count(db_session, chat.id)
    assert count == 0


# ── get_triggers_paginated ───────────────────────────────────────────────────


async def test_get_triggers_paginated_basic(db_session):
    chat = await create_chat(db_session)
    for i in range(5):
        await create_trigger(db_session, chat_id=chat.id, key_phrase=f"p{i}")
    await db_session.commit()

    triggers, total = await trigger_service.get_triggers_paginated(db_session, chat.id, page=1, page_size=3)
    assert total == 5
    assert len(triggers) == 3


async def test_get_triggers_paginated_second_page(db_session):
    chat = await create_chat(db_session)
    for i in range(5):
        await create_trigger(db_session, chat_id=chat.id, key_phrase=f"pp{i}")
    await db_session.commit()

    triggers, total = await trigger_service.get_triggers_paginated(db_session, chat.id, page=2, page_size=3)
    assert total == 5
    assert len(triggers) == 2


async def test_get_triggers_paginated_excludes_deleted(db_session):
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="pag_alive")
    await create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="pag_dead",
        is_deleted=True,
        deleted_at=datetime.now(timezone.utc),
    )
    await db_session.commit()

    triggers, total = await trigger_service.get_triggers_paginated(db_session, chat.id, page=1, page_size=10)
    assert total == 1
    assert len(triggers) == 1


# ── get_triggers_filtered ────────────────────────────────────────────────────


async def test_get_triggers_filtered_by_status(db_session):
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="f_safe", moderation_status=ModerationStatus.SAFE)
    await create_trigger(
        db_session, chat_id=chat.id, key_phrase="f_pending", moderation_status=ModerationStatus.PENDING
    )
    await db_session.commit()

    triggers, total = await trigger_service.get_triggers_filtered(db_session, page=1, limit=10, status="safe")
    assert total == 1
    assert triggers[0].key_phrase == "f_safe"


async def test_get_triggers_filtered_by_search(db_session):
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="hello_world")
    await create_trigger(db_session, chat_id=chat.id, key_phrase="goodbye")
    await db_session.commit()

    triggers, total = await trigger_service.get_triggers_filtered(db_session, page=1, limit=10, search="hello")
    assert total == 1
    assert triggers[0].key_phrase == "hello_world"


async def test_get_triggers_filtered_excludes_soft_deleted(db_session):
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="ff_alive")
    await create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="ff_dead",
        is_deleted=True,
        deleted_at=datetime.now(timezone.utc),
    )
    await db_session.commit()

    triggers, total = await trigger_service.get_triggers_filtered(db_session, page=1, limit=10)
    assert total == 1


async def test_get_triggers_filtered_excludes_banned_chats(db_session):
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="banned_t")
    await create_banned_chat(db_session, chat_id=chat.id)
    await db_session.commit()

    triggers, total = await trigger_service.get_triggers_filtered(db_session, page=1, limit=10)
    assert total == 0


async def test_get_triggers_filtered_all_status(db_session):
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="all1", moderation_status=ModerationStatus.SAFE)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="all2", moderation_status=ModerationStatus.PENDING)
    await db_session.commit()

    triggers, total = await trigger_service.get_triggers_filtered(db_session, page=1, limit=10, status="all")
    assert total == 2


async def test_get_triggers_filtered_tie_breaker_no_duplicates_no_gaps(db_session):
    """При одинаковом created_at пагинация триггеров не должна давать дублей и пропусков."""
    chat = await create_chat(db_session)
    same_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    triggers = [
        await create_trigger(db_session, chat_id=chat.id, key_phrase=f"tie_{i}", created_at=same_time) for i in range(4)
    ]
    await db_session.commit()

    page1, total = await trigger_service.get_triggers_filtered(db_session, page=1, limit=2)
    page2, _ = await trigger_service.get_triggers_filtered(db_session, page=2, limit=2)

    ids_page1 = {t.id for t in page1}
    ids_page2 = {t.id for t in page2}

    assert total == 4
    assert len(ids_page1) == 2
    assert len(ids_page2) == 2
    assert ids_page1.isdisjoint(ids_page2)
    assert ids_page1 | ids_page2 == {t.id for t in triggers}


async def test_get_triggers_filtered_numeric_search_matches_id_and_key_phrase(db_session):
    """Числовой поиск должен находить и по точному совпадению ID, и по вхождению цифр в key_phrase."""
    chat = await create_chat(db_session)
    by_id = await create_trigger(db_session, chat_id=chat.id, key_phrase="unrelated_key")
    await db_session.commit()

    # key_phrase содержит число (id триггера by_id) как подстроку — раньше числовой поиск такое не находил
    by_key = await create_trigger(db_session, chat_id=chat.id, key_phrase=f"promo_{by_id.id}_2025")
    await db_session.commit()

    triggers, total = await trigger_service.get_triggers_filtered(db_session, page=1, limit=10, search=str(by_id.id))

    ids = {t.id for t in triggers}
    assert total == 2
    assert by_id.id in ids
    assert by_key.id in ids


# ── get_triggers_stats ───────────────────────────────────────────────────────


async def test_get_triggers_stats_counts_by_status(db_session):
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="s1", moderation_status=ModerationStatus.SAFE)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="s2", moderation_status=ModerationStatus.SAFE)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="s3", moderation_status=ModerationStatus.FLAGGED)
    await db_session.commit()

    stats = await trigger_service.get_triggers_stats(db_session)
    assert stats["safe"] == 2
    assert stats["flagged"] == 1
    assert stats["pending"] == 0


async def test_get_triggers_stats_excludes_deleted(db_session):
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="st_alive", moderation_status=ModerationStatus.SAFE)
    await create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="st_dead",
        moderation_status=ModerationStatus.SAFE,
        is_deleted=True,
        deleted_at=datetime.now(timezone.utc),
    )
    await db_session.commit()

    stats = await trigger_service.get_triggers_stats(db_session)
    assert stats["safe"] == 1


async def test_get_triggers_stats_excludes_banned_chats(db_session):
    chat = await create_chat(db_session)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="ban_stat")
    await create_banned_chat(db_session, chat_id=chat.id)
    await db_session.commit()

    stats = await trigger_service.get_triggers_stats(db_session)
    # Main moderation statuses should be zero since the chat is banned
    assert stats["safe"] == 0
    assert stats["pending"] == 0
    assert stats["flagged"] == 0
    assert stats["deleted"] == 0
    # But banned_chat count should reflect the trigger
    assert stats["banned_chat"] == 1


async def test_get_triggers_stats_deleted_in_banned_chat_counted_once(db_session):
    """Триггер, мягко удалённый в забаненном чате, должен попадать только в banned_chat, не в deleted тоже."""
    chat = await create_chat(db_session)
    await create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="del_banned",
        is_deleted=True,
        deleted_at=datetime.now(timezone.utc),
    )
    await create_banned_chat(db_session, chat_id=chat.id)
    await db_session.commit()

    stats = await trigger_service.get_triggers_stats(db_session)

    assert stats["banned_chat"] == 1
    assert stats["deleted"] == 0


# ── approve_trigger ──────────────────────────────────────────────────────────


async def test_approve_trigger(db_session):
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    admin = await create_user(db_session, first_name="Admin")
    trigger = await create_trigger(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        moderation_status=ModerationStatus.PENDING,
    )
    await db_session.commit()

    admin_id = admin.id
    result = await trigger_service.approve_trigger(db_session, trigger.id, admin_id)
    assert result is not None
    assert result.moderation_status == ModerationStatus.SAFE
    assert f"Admin {admin_id}" in result.moderation_reason


async def test_approve_trigger_nonexistent(db_session):
    result = await trigger_service.approve_trigger(db_session, 999999, admin_id=1)
    assert result is None


async def test_approve_trigger_flagged_increments_chat_false_positive_count(db_session):
    """Одобрение FLAGGED-триггера — ложное срабатывание модерации, счётчик чата растёт."""
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    admin = await create_user(db_session, first_name="Admin")
    trigger = await create_trigger(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        moderation_status=ModerationStatus.FLAGGED,
    )
    await db_session.commit()

    await trigger_service.approve_trigger(db_session, trigger.id, admin.id)

    await db_session.refresh(chat)
    assert chat.moderation_false_positive_count == 1


async def test_approve_trigger_already_safe_does_not_change_false_positive_count(db_session):
    """Повторное одобрение уже-Safe триггера не считается ложным срабатыванием."""
    chat = await create_chat(db_session)
    user = await create_user(db_session)
    admin = await create_user(db_session, first_name="Admin")
    trigger = await create_trigger(
        db_session,
        chat_id=chat.id,
        user_id=user.id,
        moderation_status=ModerationStatus.SAFE,
    )
    await db_session.commit()

    await trigger_service.approve_trigger(db_session, trigger.id, admin.id)

    await db_session.refresh(chat)
    assert chat.moderation_false_positive_count == 0


# ── requeue_trigger ──────────────────────────────────────────────────────────


async def test_requeue_trigger(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(
        db_session,
        chat_id=chat.id,
        moderation_status=ModerationStatus.FLAGGED,
    )
    await db_session.commit()

    result = await trigger_service.requeue_trigger(db_session, trigger.id)
    assert result is not None
    assert result.moderation_status == ModerationStatus.PENDING


async def test_requeue_trigger_nonexistent(db_session):
    result = await trigger_service.requeue_trigger(db_session, 999999)
    assert result is None


# ── increment_usage ──────────────────────────────────────────────────────────


async def test_increment_usage(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id)
    await db_session.commit()

    assert trigger.usage_count == 0

    await trigger_service.increment_usage(db_session, trigger.id)

    await db_session.refresh(trigger)
    assert trigger.usage_count == 1


async def test_increment_usage_creates_daily_stat(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id)
    await db_session.commit()

    await trigger_service.increment_usage(db_session, trigger.id)

    stmt = select(DailyStat)
    result = await db_session.execute(stmt)
    stat = result.scalars().first()
    assert stat is not None
    assert stat.triggers_count == 1


async def test_increment_usage_multiple_times(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id)
    await db_session.commit()

    for _ in range(3):
        await trigger_service.increment_usage(db_session, trigger.id)

    await db_session.refresh(trigger)
    assert trigger.usage_count == 3


# ── bulk_remoderate_safe ─────────────────────────────────────────────────────


async def test_bulk_remoderate_safe(db_session):
    chat = await create_chat(db_session)
    await create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="bs1",
        moderation_status=ModerationStatus.SAFE,
    )
    await create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="bs2",
        moderation_status=ModerationStatus.SAFE,
    )
    await db_session.commit()

    count = await trigger_service.bulk_remoderate_safe(db_session)
    assert count == 2


async def test_bulk_remoderate_excludes_deleted(db_session):
    chat = await create_chat(db_session)
    await create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="brd_alive",
        moderation_status=ModerationStatus.SAFE,
    )
    await create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="brd_dead",
        moderation_status=ModerationStatus.SAFE,
        is_deleted=True,
        deleted_at=datetime.now(timezone.utc),
    )
    await db_session.commit()

    count = await trigger_service.bulk_remoderate_safe(db_session)
    assert count == 1


async def test_bulk_remoderate_excludes_banned_chats(db_session):
    chat = await create_chat(db_session)
    await create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="brb",
        moderation_status=ModerationStatus.SAFE,
    )
    await create_banned_chat(db_session, chat_id=chat.id)
    await db_session.commit()

    count = await trigger_service.bulk_remoderate_safe(db_session)
    assert count == 0


async def test_bulk_remoderate_empty(db_session):
    count = await trigger_service.bulk_remoderate_safe(db_session)
    assert count == 0


async def test_bulk_remoderate_excludes_flagged_status(db_session):
    chat = await create_chat(db_session)
    await create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="flagged_one",
        moderation_status=ModerationStatus.FLAGGED,
    )
    await db_session.commit()

    count = await trigger_service.bulk_remoderate_safe(db_session)
    assert count == 0


# ── Edge cases ───────────────────────────────────────────────────────────────


async def test_delete_trigger_by_key_clears_cache(db_session):
    from app.core.valkey import valkey

    chat = await create_chat(db_session)
    await create_trigger(db_session, chat_id=chat.id, key_phrase="cache_del")
    await db_session.commit()

    await trigger_service.delete_trigger_by_key(db_session, chat.id, "cache_del")
    valkey.delete.assert_called()


async def test_get_triggers_filtered_by_chat_id(db_session):
    chat1 = await create_chat(db_session)
    chat2 = await create_chat(db_session)
    await create_trigger(db_session, chat_id=chat1.id, key_phrase="fc1")
    await create_trigger(db_session, chat_id=chat2.id, key_phrase="fc2")
    await db_session.commit()

    triggers, total = await trigger_service.get_triggers_filtered(db_session, page=1, limit=10, chat_id=chat1.id)
    assert total == 1
    assert triggers[0].key_phrase == "fc1"


async def test_update_trigger_basic(db_session):
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id, key_phrase="old_key")
    await db_session.commit()

    updated = await trigger_service.update_trigger(db_session, trigger.id, key_phrase="new_key")
    assert updated is not None
    assert updated.key_phrase == "new_key"


async def test_update_trigger_nonexistent(db_session):
    result = await trigger_service.update_trigger(db_session, 999999, key_phrase="nope")
    assert result is None


# ── Utility functions ────────────────────────────────────────────────────────


async def test_get_file_id_from_content_photo():
    content = {"photo": [{"file_id": "sm"}, {"file_id": "lg"}]}
    assert trigger_service.get_file_id_from_content(content) == "lg"


async def test_get_file_id_from_content_video():
    content = {"video": {"file_id": "vid123"}}
    assert trigger_service.get_file_id_from_content(content) == "vid123"


async def test_get_file_id_from_content_none():
    content = {"text": "no file"}
    assert trigger_service.get_file_id_from_content(content) is None


async def test_get_file_type_from_content():
    assert trigger_service.get_file_type_from_content({"sticker": {"file_id": "s"}}) == "sticker"
    assert trigger_service.get_file_type_from_content({"text": "hi"}) is None


async def test_get_file_info_from_content():
    file_id, file_type = trigger_service.get_file_info_from_content({"animation": {"file_id": "anim1"}})
    assert file_id == "anim1"
    assert file_type == "animation"


async def test_validate_regex_valid():
    result = await trigger_service.validate_regex(r"\d+")
    assert result is None


async def test_validate_regex_invalid():
    result = await trigger_service.validate_regex(r"[invalid")
    assert result is not None
    assert "Invalid regex" in result


async def test_validate_regex_too_long():
    result = await trigger_service.validate_regex("a" * 600)
    assert result is not None
    assert "too long" in result


# ── Trigger.rich default + create_trigger(rich=True) ─────────────────────────


async def test_create_trigger_with_rich_flag(db_session):
    """create_trigger с rich=True должен сохранять Trigger.rich == True."""
    chat = await create_chat(db_session)
    await db_session.commit()

    trigger = await trigger_service.create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="rich_flag_test",
        content={"text": "<h1>Hello</h1>"},
        created_by=None,
        skip_moderation=True,
        rich=True,
    )

    assert trigger.rich is True
    assert trigger.is_template is False  # rich не форсирует is_template на уровне сервиса


async def test_trigger_rich_defaults_to_false(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    trigger = Trigger(
        chat_id=chat.id,
        key_phrase="rich_default_test",
        content={"text": "x"},
    )
    db_session.add(trigger)
    await db_session.flush()
    await db_session.commit()
    await db_session.refresh(trigger)

    assert trigger.rich is False


# ── get_triggers_by_chat: rich сохраняется через кэш (8a) ─────────────────────


async def test_get_triggers_by_chat_rich_survives_cache_roundtrip(db_session, _mock_valkey_for_services):
    """rich=True должен сохраняться после сериализации в Valkey и десериализации обратно.

    Первый вызов — cache miss → читает из БД, сериализует в Valkey.
    Второй вызов — cache hit → десериализует из Valkey.
    На обоих этапах trigger.rich должен быть True.
    """
    import json

    chat = await create_chat(db_session)
    await trigger_service.create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="rich_cache_test",
        content={"text": "<h1>Hello</h1>"},
        created_by=None,
        skip_moderation=True,
        rich=True,
    )
    await db_session.commit()

    # Первый вызов — cache miss (mock.get возвращает None по умолчанию)
    triggers_first = await trigger_service.get_triggers_by_chat(db_session, chat.id)
    assert len(triggers_first) == 1
    assert triggers_first[0].rich is True, "rich должен быть True при первом (DB) вызове"

    # Извлекаем сериализованные данные, сохранённые в mock.set
    set_call = _mock_valkey_for_services.set.call_args
    cache_key, serialized_json = set_call[0][0], set_call[0][1]

    # Настраиваем mock.get вернуть эти данные при следующем вызове
    _mock_valkey_for_services.get = __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(
        return_value=serialized_json
    )

    # Второй вызов — cache hit
    triggers_second = await trigger_service.get_triggers_by_chat(db_session, chat.id)
    assert len(triggers_second) == 1
    assert triggers_second[0].rich is True, "rich должен быть True после десериализации из Valkey"


# ── rich content degraded before moderation ──────────────────────────────────


def _published_task(mock_broker):
    """Извлечь TriggerModerationTask из вызова broker.publish."""
    mock_broker.publish.assert_awaited()
    return mock_broker.publish.call_args[0][0]


async def test_create_trigger_rich_degrades_text_for_moderation(db_session, _mock_broker_for_services):
    chat = await create_chat(db_session)
    await db_session.commit()

    content = {"text": '<h1>Spam</h1><p>buy <b>now</b> <a href="https://x">link</a></p>'}
    await trigger_service.create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="rich_spam",
        content=content,
        created_by=None,
        skip_moderation=False,
        rich=True,
    )

    task = _published_task(_mock_broker_for_services)
    # Структурные теги срезаны
    assert "<h1>" not in task.text_content
    assert "<p>" not in task.text_content
    # Текст и ссылка сохранены (degrade оставляет текст и <a href>)
    assert "Spam" in task.text_content
    assert "link" in task.text_content
    assert "https://x" in task.text_content


async def test_create_trigger_non_rich_text_passes_through(db_session, _mock_broker_for_services):
    chat = await create_chat(db_session)
    await db_session.commit()

    content = {"text": "<h1>Spam</h1> buy now"}
    await trigger_service.create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="plain_text",
        content=content,
        created_by=None,
        skip_moderation=False,
        rich=False,
    )

    task = _published_task(_mock_broker_for_services)
    # Для не-rich триггера degrade не применяется — текст уходит как есть
    assert task.text_content == "<h1>Spam</h1> buy now"


async def test_requeue_trigger_rich_degrades_text_for_moderation(db_session, _mock_broker_for_services):
    chat = await create_chat(db_session)
    trigger = await create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="rich_requeue",
        content={"text": '<h1>Spam</h1><p>buy <a href="https://x">link</a></p>'},
        rich=True,
    )
    await db_session.commit()
    _mock_broker_for_services.publish.reset_mock()

    await trigger_service.requeue_trigger(db_session, trigger.id)

    task = _published_task(_mock_broker_for_services)
    assert "<h1>" not in task.text_content
    assert "<p>" not in task.text_content
    assert "Spam" in task.text_content
    assert "link" in task.text_content


async def test_bulk_remoderate_rich_degrades_text_for_moderation(db_session, _mock_broker_for_services):
    chat = await create_chat(db_session)
    await create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="rich_bulk",
        content={"text": '<h1>Spam</h1><p>buy <a href="https://x">link</a></p>'},
        rich=True,
        moderation_status=ModerationStatus.SAFE,
    )
    await db_session.commit()
    _mock_broker_for_services.publish.reset_mock()

    count = await trigger_service.bulk_remoderate_safe(db_session)
    assert count == 1

    task = _published_task(_mock_broker_for_services)
    assert "<h1>" not in task.text_content
    assert "<p>" not in task.text_content
    assert "Spam" in task.text_content
    assert "link" in task.text_content
