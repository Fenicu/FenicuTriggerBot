"""Integration tests for app/services/chat_service.py."""

from datetime import datetime, timezone

from app.db.models.chat import BannedChat, Chat
from app.db.models.user_chat import UserChat
from app.services import chat_service
from tests.factories import create_banned_chat, create_chat, create_trigger, create_user


# ── get_or_create_chat ───────────────────────────────────────────────────────


async def test_get_or_create_chat_creates_new(db_session):
    chat = await chat_service.get_or_create_chat(db_session, chat_id=-100999, title="New Chat", type="supergroup")

    assert chat.id == -100999
    assert chat.title == "New Chat"
    assert chat.type == "supergroup"


async def test_get_or_create_chat_updates_existing(db_session):
    chat = await create_chat(db_session, title="Old Title")
    await db_session.commit()
    chat_id = chat.id

    # Expire cached attributes so the upsert result reflects DB state
    db_session.expire(chat)

    updated = await chat_service.get_or_create_chat(db_session, chat_id=chat_id, title="New Title", type="supergroup")

    assert updated.id == chat_id
    assert updated.title == "New Title"


async def test_get_or_create_chat_sets_is_active(db_session):
    chat = await chat_service.get_or_create_chat(db_session, chat_id=-100888, title="Active Chat", is_active=False)

    assert chat.is_active is False


async def test_get_or_create_chat_preserves_is_active_when_none(db_session):
    chat = await create_chat(db_session, is_active=True)
    await db_session.commit()

    updated = await chat_service.get_or_create_chat(db_session, chat_id=chat.id, title="Updated", is_active=None)

    assert updated.is_active is True


# ── get_chat_with_ban_status ─────────────────────────────────────────────────


async def test_get_chat_with_ban_status_not_banned(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    result_chat, banned = await chat_service.get_chat_with_ban_status(db_session, chat.id)
    assert result_chat is not None
    assert result_chat.id == chat.id
    assert banned is None


async def test_get_chat_with_ban_status_banned(db_session):
    chat = await create_chat(db_session)
    await create_banned_chat(db_session, chat_id=chat.id, reason="spam")
    await db_session.commit()

    result_chat, banned = await chat_service.get_chat_with_ban_status(db_session, chat.id)
    assert result_chat is not None
    assert banned is not None
    assert banned.reason == "spam"


async def test_get_chat_with_ban_status_nonexistent(db_session):
    result_chat, banned = await chat_service.get_chat_with_ban_status(db_session, -99999999)
    assert result_chat is None
    assert banned is None


# ── ban_chat / unban_chat ────────────────────────────────────────────────────


async def test_ban_chat(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    banned = await chat_service.ban_chat(db_session, chat.id, reason="abuse")
    assert banned.chat_id == chat.id
    assert banned.reason == "abuse"


async def test_ban_chat_idempotent(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    first = await chat_service.ban_chat(db_session, chat.id, reason="first")
    second = await chat_service.ban_chat(db_session, chat.id, reason="second")

    # Should return the existing ban, not create a new one
    assert first.chat_id == second.chat_id
    assert second.reason == "first"  # not updated


async def test_unban_chat(db_session):
    chat = await create_chat(db_session)
    await create_banned_chat(db_session, chat_id=chat.id)
    await db_session.commit()

    await chat_service.unban_chat(db_session, chat.id)

    result = await db_session.get(BannedChat, chat.id)
    assert result is None


async def test_unban_chat_not_banned(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    # Should not raise
    await chat_service.unban_chat(db_session, chat.id)


# ── update_chat_settings ─────────────────────────────────────────────────────


async def test_update_chat_settings_existing_chat(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    updated = await chat_service.update_chat_settings(db_session, chat.id, language_code="en", warn_limit=5)

    assert updated.language_code == "en"
    assert updated.warn_limit == 5


async def test_update_chat_settings_creates_if_not_exists(db_session):
    chat_id = -100777888
    updated = await chat_service.update_chat_settings(db_session, chat_id, language_code="es")

    assert updated.id == chat_id
    assert updated.language_code == "es"


async def test_update_chat_settings_ignores_unknown_attrs(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    # Should not raise for unknown attributes
    updated = await chat_service.update_chat_settings(db_session, chat.id, nonexistent_field="value")
    assert updated.id == chat.id


# ── update_chat_settings_specific ────────────────────────────────────────────


async def test_update_chat_settings_specific_timezone(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    updated = await chat_service.update_chat_settings_specific(db_session, chat.id, timezone="Europe/Moscow")
    assert updated.timezone == "Europe/Moscow"


async def test_update_chat_settings_specific_modules(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    updated = await chat_service.update_chat_settings_specific(
        db_session, chat.id, module_triggers=False, module_moderation=False
    )
    assert updated.module_triggers is False
    assert updated.module_moderation is False


async def test_update_chat_settings_specific_none_values_unchanged(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    # All None should leave defaults
    updated = await chat_service.update_chat_settings_specific(db_session, chat.id)
    assert updated.timezone == "UTC"  # default
    assert updated.module_triggers is True  # default


# ── update_language ──────────────────────────────────────────────────────────


async def test_update_language(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    updated = await chat_service.update_language(db_session, chat.id, "en")
    assert updated.language_code == "en"


# ── get_chats ────────────────────────────────────────────────────────────────


async def test_get_chats_basic_pagination(db_session):
    for i in range(5):
        await create_chat(db_session, title=f"Chat {i}", type="supergroup")
    await db_session.commit()

    rows, total = await chat_service.get_chats(db_session, page=1, limit=3)
    assert total == 5
    assert len(rows) == 3


async def test_get_chats_second_page(db_session):
    for i in range(5):
        await create_chat(db_session, title=f"Page Chat {i}", type="supergroup")
    await db_session.commit()

    rows, total = await chat_service.get_chats(db_session, page=2, limit=3)
    assert total == 5
    assert len(rows) == 2


async def test_get_chats_query_by_title(db_session):
    await create_chat(db_session, title="Alpha Group", type="supergroup")
    await create_chat(db_session, title="Beta Group", type="supergroup")
    await db_session.commit()

    rows, total = await chat_service.get_chats(db_session, query="Alpha")
    assert total == 1


async def test_get_chats_excludes_private_by_default(db_session):
    await create_chat(db_session, title="Public", type="supergroup")
    await create_chat(db_session, title="DM", type="private")
    await db_session.commit()

    rows, total = await chat_service.get_chats(db_session, include_private=False)
    assert total == 1


async def test_get_chats_include_private(db_session):
    await create_chat(db_session, title="Public", type="supergroup")
    await create_chat(db_session, title="DM", type="private")
    await db_session.commit()

    rows, total = await chat_service.get_chats(db_session, include_private=True)
    assert total == 2


async def test_get_chats_filter_by_is_active(db_session):
    await create_chat(db_session, title="Active", type="supergroup", is_active=True)
    await create_chat(db_session, title="Inactive", type="supergroup", is_active=False)
    await db_session.commit()

    rows, total = await chat_service.get_chats(db_session, is_active=True)
    assert total == 1


async def test_get_chats_filter_by_is_banned(db_session):
    chat1 = await create_chat(db_session, title="Good Chat", type="supergroup")
    chat2 = await create_chat(db_session, title="Bad Chat", type="supergroup")
    await create_banned_chat(db_session, chat_id=chat2.id)
    await db_session.commit()

    rows_banned, total_banned = await chat_service.get_chats(db_session, is_banned=True)
    assert total_banned == 1

    rows_not_banned, total_not_banned = await chat_service.get_chats(db_session, is_banned=False)
    assert total_not_banned == 1


async def test_get_chats_triggers_count_excludes_soft_deleted(db_session):
    chat = await create_chat(db_session, title="Counted", type="supergroup")
    await create_trigger(db_session, chat_id=chat.id, key_phrase="alive_t")
    await create_trigger(
        db_session,
        chat_id=chat.id,
        key_phrase="dead_t",
        is_deleted=True,
        deleted_at=datetime.now(timezone.utc),
    )
    await db_session.commit()

    rows, total = await chat_service.get_chats(db_session, page=1, limit=10)
    assert total == 1
    # rows is a list of tuples: (Chat, BannedChat | None, triggers_count, users_count)
    chat_row, banned_row, triggers_count, users_count = rows[0]
    assert triggers_count == 1  # only the non-deleted trigger


async def test_get_chats_sort_by_title(db_session):
    await create_chat(db_session, title="Zebra", type="supergroup")
    await create_chat(db_session, title="Alpha", type="supergroup")
    await db_session.commit()

    rows, _ = await chat_service.get_chats(db_session, sort_by="title", sort_order="asc")
    titles = [r[0].title for r in rows]
    assert titles == ["Alpha", "Zebra"]


async def test_get_chats_filter_by_chat_type(db_session):
    await create_chat(db_session, title="SG", type="supergroup")
    await create_chat(db_session, title="Grp", type="group")
    await db_session.commit()

    rows, total = await chat_service.get_chats(db_session, chat_type="group")
    assert total == 1
    assert rows[0][0].title == "Grp"


async def test_get_chats_empty(db_session):
    rows, total = await chat_service.get_chats(db_session)
    assert total == 0
    assert rows == []


# ── get_chat_users ───────────────────────────────────────────────────────────


async def test_get_chat_users_basic(db_session):
    chat = await create_chat(db_session)
    user1 = await create_user(db_session, first_name="Alice")
    user2 = await create_user(db_session, first_name="Bob")
    uc1 = UserChat(user_id=user1.id, chat_id=chat.id, is_active=True)
    uc2 = UserChat(user_id=user2.id, chat_id=chat.id, is_active=True)
    db_session.add_all([uc1, uc2])
    await db_session.commit()

    users, total = await chat_service.get_chat_users(db_session, chat.id)
    assert total == 2
    assert len(users) == 2


async def test_get_chat_users_pagination(db_session):
    chat = await create_chat(db_session)
    for _ in range(5):
        user = await create_user(db_session)
        db_session.add(UserChat(user_id=user.id, chat_id=chat.id, is_active=True))
    await db_session.commit()

    users, total = await chat_service.get_chat_users(db_session, chat.id, page=1, limit=3)
    assert total == 5
    assert len(users) == 3


async def test_get_chat_users_empty(db_session):
    chat = await create_chat(db_session)
    await db_session.commit()

    users, total = await chat_service.get_chat_users(db_session, chat.id)
    assert total == 0
    assert users == []


async def test_get_chats_filter_by_is_trusted(db_session):
    await create_chat(db_session, title="Trusted", type="supergroup", is_trusted=True)
    await create_chat(db_session, title="Not Trusted", type="supergroup", is_trusted=False)
    await db_session.commit()

    rows, total = await chat_service.get_chats(db_session, is_trusted=True)
    assert total == 1
    assert rows[0][0].title == "Trusted"


# ── get_chats: tie-breaker / NULLS LAST / поиск по username ─────────────────


async def test_get_chats_tie_breaker_no_duplicates_no_gaps(db_session):
    """При одинаковом sort-значении (created_at) пагинация не должна давать дублей и пропусков."""
    same_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    chats = [await create_chat(db_session, title=f"Tie {i}", type="supergroup", created_at=same_time) for i in range(4)]
    await db_session.commit()

    page1, total = await chat_service.get_chats(db_session, page=1, limit=2)
    page2, _ = await chat_service.get_chats(db_session, page=2, limit=2)

    ids_page1 = {row[0].id for row in page1}
    ids_page2 = {row[0].id for row in page2}

    assert total == 4
    assert len(ids_page1) == 2
    assert len(ids_page2) == 2
    assert ids_page1.isdisjoint(ids_page2)
    assert ids_page1 | ids_page2 == {c.id for c in chats}


async def test_get_chats_search_by_username(db_session):
    """Поиск чата должен находить совпадение по username, не только по id/title."""
    await create_chat(db_session, title="Whatever", username="fenicu_chat", type="supergroup")
    await create_chat(db_session, title="Other", username="another_one", type="supergroup")
    await db_session.commit()

    rows, total = await chat_service.get_chats(db_session, query="fenicu")
    assert total == 1
    assert rows[0][0].username == "fenicu_chat"


async def test_get_chats_sort_by_username_nulls_last_desc(db_session):
    """Чаты без username не должны оказываться в начале при sort_by=username&sort_order=desc."""
    await create_chat(db_session, title="Has Username", username="zzz", type="supergroup")
    await create_chat(db_session, title="No Username", username=None, type="supergroup")
    await db_session.commit()

    rows, total = await chat_service.get_chats(db_session, sort_by="username", sort_order="desc")
    assert total == 2
    assert rows[-1][0].username is None


# ── get_chat_users: tie-breaker ──────────────────────────────────────────────


async def test_get_chat_users_tie_breaker_no_duplicates_no_gaps(db_session):
    """При одинаковом updated_at у UserChat пагинация не должна давать дублей/пропусков."""
    chat = await create_chat(db_session)
    same_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    user_ids = []
    for i in range(4):
        user = await create_user(db_session, first_name=f"Tie{i}")
        uc = UserChat(user_id=user.id, chat_id=chat.id, is_active=True, updated_at=same_time)
        db_session.add(uc)
        user_ids.append(user.id)
    await db_session.commit()

    page1, total = await chat_service.get_chat_users(db_session, chat.id, page=1, limit=2)
    page2, _ = await chat_service.get_chat_users(db_session, chat.id, page=2, limit=2)

    ids_page1 = {uc.user_id for uc in page1}
    ids_page2 = {uc.user_id for uc in page2}

    assert total == 4
    assert ids_page1.isdisjoint(ids_page2)
    assert ids_page1 | ids_page2 == set(user_ids)
