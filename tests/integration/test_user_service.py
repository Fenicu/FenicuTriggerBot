"""Integration tests for app/services/user_service.py."""

from sqlalchemy import select

from app.db.models.moderation_history import ModerationHistory, ModerationStep
from app.db.models.trigger import Trigger
from app.db.models.user import User
from app.db.models.user_chat import UserChat
from app.db.models.warn import Warn
from app.services import user_service
from app.services.moderation_history_service import add_history_step
from tests.factories import create_chat, create_trigger, create_user, create_warn


# ── get_or_create_user ───────────────────────────────────────────────────────


async def test_get_or_create_user_creates_new(db_session):
    user = await user_service.get_or_create_user(
        db_session,
        user_id=111222,
        username="alice",
        first_name="Alice",
        last_name="Smith",
        language_code="en",
    )

    assert user.id == 111222
    assert user.username == "alice"
    assert user.first_name == "Alice"
    assert user.last_name == "Smith"
    assert user.language_code == "en"


async def test_get_or_create_user_updates_existing(db_session):
    user = await create_user(db_session, username="old_name", first_name="Old")
    await db_session.commit()
    user_id = user.id

    # Expire cached attributes so the upsert result reflects DB state
    db_session.expire(user)

    updated = await user_service.get_or_create_user(
        db_session,
        user_id=user_id,
        username="new_name",
        first_name="New",
    )

    assert updated.id == user_id
    assert updated.username == "new_name"
    assert updated.first_name == "New"


async def test_get_or_create_user_sets_premium(db_session):
    user = await user_service.get_or_create_user(
        db_session, user_id=333444, is_premium=True
    )
    assert user.is_premium is True


async def test_get_or_create_user_sets_is_bot(db_session):
    user = await user_service.get_or_create_user(
        db_session, user_id=555666, is_bot=True
    )
    assert user.is_bot is True


# ── get_user ─────────────────────────────────────────────────────────────────


async def test_get_user_existing(db_session):
    created = await create_user(db_session, first_name="Found")
    await db_session.commit()

    user = await user_service.get_user(db_session, created.id)
    assert user is not None
    assert user.id == created.id
    assert user.first_name == "Found"


async def test_get_user_nonexistent(db_session):
    user = await user_service.get_user(db_session, 999999999)
    assert user is None


# ── get_users ────────────────────────────────────────────────────────────────


async def test_get_users_basic_pagination(db_session):
    for i in range(5):
        await create_user(db_session, first_name=f"User{i}")
    await db_session.commit()

    users, total = await user_service.get_users(db_session, page=1, limit=3)
    assert total == 5
    assert len(users) == 3


async def test_get_users_second_page(db_session):
    for i in range(5):
        await create_user(db_session, first_name=f"Pager{i}")
    await db_session.commit()

    users, total = await user_service.get_users(db_session, page=2, limit=3)
    assert total == 5
    assert len(users) == 2


async def test_get_users_query_by_username(db_session):
    await create_user(db_session, username="target_user", first_name="Target")
    await create_user(db_session, username="other_user", first_name="Other")
    await db_session.commit()

    users, total = await user_service.get_users(db_session, query="target")
    assert total == 1
    assert users[0].username == "target_user"


async def test_get_users_query_by_first_name(db_session):
    await create_user(db_session, first_name="UniqueNameXYZ")
    await create_user(db_session, first_name="Someone")
    await db_session.commit()

    users, total = await user_service.get_users(db_session, query="UniqueNameXYZ")
    assert total == 1


async def test_get_users_query_by_id(db_session):
    user = await create_user(db_session)
    await db_session.commit()

    users, total = await user_service.get_users(db_session, query=str(user.id))
    assert total == 1
    assert users[0].id == user.id


async def test_get_users_filter_by_premium(db_session):
    await create_user(db_session, is_premium=True, first_name="Premium")
    await create_user(db_session, is_premium=False, first_name="Free")
    await db_session.commit()

    users, total = await user_service.get_users(db_session, is_premium=True)
    assert total == 1
    assert users[0].first_name == "Premium"


async def test_get_users_filter_by_trusted(db_session):
    await create_user(db_session, is_trusted=True, first_name="Trusted")
    await create_user(db_session, is_trusted=False, first_name="Untrusted")
    await db_session.commit()

    # Note: is_trusted is a DB column, defaults to False
    users, total = await user_service.get_users(db_session, is_trusted=True)
    assert total == 1
    assert users[0].first_name == "Trusted"


async def test_get_users_filter_by_moderator(db_session):
    await create_user(db_session, is_bot_moderator=True, first_name="Mod")
    await create_user(db_session, is_bot_moderator=False, first_name="Regular")
    await db_session.commit()

    users, total = await user_service.get_users(db_session, is_bot_moderator=True)
    assert total == 1
    assert users[0].first_name == "Mod"


async def test_get_users_sort_order_asc(db_session):
    u1 = await create_user(db_session, first_name="AAA")
    u2 = await create_user(db_session, first_name="ZZZ")
    await db_session.commit()

    users, total = await user_service.get_users(
        db_session, sort_by="first_name", sort_order="asc"
    )
    assert users[0].first_name == "AAA"
    assert users[1].first_name == "ZZZ"


async def test_get_users_empty(db_session):
    users, total = await user_service.get_users(db_session)
    assert total == 0
    assert users == []


# ── get_user_by_username ─────────────────────────────────────────────────────


async def test_get_user_by_username_existing(db_session):
    await create_user(db_session, username="findme")
    await db_session.commit()

    user = await user_service.get_user_by_username(db_session, "findme")
    assert user is not None
    assert user.username == "findme"


async def test_get_user_by_username_with_at_prefix(db_session):
    await create_user(db_session, username="withprefix")
    await db_session.commit()

    user = await user_service.get_user_by_username(db_session, "@withprefix")
    assert user is not None
    assert user.username == "withprefix"


async def test_get_user_by_username_nonexistent(db_session):
    user = await user_service.get_user_by_username(db_session, "noone")
    assert user is None


# ── get_user_chats ───────────────────────────────────────────────────────────


async def test_get_user_chats_basic(db_session):
    user = await create_user(db_session)
    chat1 = await create_chat(db_session, title="Chat A")
    chat2 = await create_chat(db_session, title="Chat B")
    db_session.add(UserChat(user_id=user.id, chat_id=chat1.id))
    db_session.add(UserChat(user_id=user.id, chat_id=chat2.id))
    await db_session.commit()

    chats, total = await user_service.get_user_chats(db_session, user.id)
    assert total == 2
    assert len(chats) == 2


async def test_get_user_chats_pagination(db_session):
    user = await create_user(db_session)
    for _ in range(5):
        chat = await create_chat(db_session)
        db_session.add(UserChat(user_id=user.id, chat_id=chat.id))
    await db_session.commit()

    chats, total = await user_service.get_user_chats(db_session, user.id, page=1, limit=3)
    assert total == 5
    assert len(chats) == 3


async def test_get_user_chats_empty(db_session):
    user = await create_user(db_session)
    await db_session.commit()

    chats, total = await user_service.get_user_chats(db_session, user.id)
    assert total == 0
    assert chats == []


# ── delete_user ──────────────────────────────────────────────────────────────


async def test_delete_user_removes_user(db_session):
    user = await create_user(db_session)
    await db_session.commit()

    await user_service.delete_user(db_session, user.id)

    result = await db_session.get(User, user.id)
    assert result is None


async def test_delete_user_nullifies_trigger_created_by(db_session):
    user = await create_user(db_session)
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id, user_id=user.id)
    await db_session.commit()

    await user_service.delete_user(db_session, user.id)

    await db_session.refresh(trigger)
    assert trigger.created_by is None


async def test_delete_user_removes_warns_as_subject(db_session):
    user = await create_user(db_session)
    chat = await create_chat(db_session)
    await create_warn(db_session, chat_id=chat.id, user_id=user.id)
    await db_session.commit()

    await user_service.delete_user(db_session, user.id)

    stmt = select(Warn).where(Warn.user_id == user.id)
    result = await db_session.execute(stmt)
    assert result.scalars().all() == []


async def test_delete_user_nullifies_warns_as_admin(db_session):
    admin = await create_user(db_session, first_name="Admin")
    target = await create_user(db_session, first_name="Target")
    chat = await create_chat(db_session)
    warn = await create_warn(db_session, chat_id=chat.id, user_id=target.id, admin_id=admin.id)
    await db_session.commit()

    await user_service.delete_user(db_session, admin.id)

    await db_session.refresh(warn)
    assert warn.admin_id is None


async def test_delete_user_removes_user_chats(db_session):
    user = await create_user(db_session)
    chat = await create_chat(db_session)
    db_session.add(UserChat(user_id=user.id, chat_id=chat.id))
    await db_session.commit()

    await user_service.delete_user(db_session, user.id)

    stmt = select(UserChat).where(UserChat.user_id == user.id)
    result = await db_session.execute(stmt)
    assert result.scalars().all() == []


async def test_delete_user_nullifies_moderation_history_actor(db_session):
    user = await create_user(db_session)
    chat = await create_chat(db_session)
    trigger = await create_trigger(db_session, chat_id=chat.id)
    await db_session.commit()

    await add_history_step(
        db_session,
        trigger.id,
        ModerationStep.MANUAL_APPROVED,
        actor_id=user.id,
    )
    await db_session.commit()

    await user_service.delete_user(db_session, user.id)

    stmt = select(ModerationHistory).where(ModerationHistory.trigger_id == trigger.id)
    result = await db_session.execute(stmt)
    history = result.scalars().first()
    assert history is not None
    assert history.actor_id is None


async def test_delete_user_nonexistent_does_not_raise(db_session):
    # Should not raise when deleting a user that doesn't exist
    await user_service.delete_user(db_session, 999999999)


async def test_get_users_sort_by_badges(db_session):
    await create_user(db_session, first_name="Regular", is_bot_moderator=False, is_trusted=False, is_premium=False)
    await create_user(db_session, first_name="ModTrusted", is_bot_moderator=True, is_trusted=True, is_premium=False)
    await create_user(db_session, first_name="PremiumOnly", is_bot_moderator=False, is_trusted=False, is_premium=True)
    await db_session.commit()

    users, total = await user_service.get_users(db_session, sort_by="badges", sort_order="desc")
    assert total == 3
    # ModTrusted has highest badge score (10+5=15), PremiumOnly has 1, Regular has 0
    assert users[0].first_name == "ModTrusted"
    assert users[1].first_name == "PremiumOnly"
    assert users[2].first_name == "Regular"
