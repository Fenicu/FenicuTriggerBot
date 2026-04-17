"""Test data factory helpers."""

from app.db.models.chat import BannedChat, Chat
from app.db.models.trigger import AccessLevel, MatchType, ModerationStatus, Trigger
from app.db.models.user import User
from app.db.models.warn import Warn
from sqlalchemy.ext.asyncio import AsyncSession

_id_counter = 0


def _next_id() -> int:
    global _id_counter
    _id_counter += 1
    return _id_counter


async def create_user(session: AsyncSession, **overrides) -> User:
    defaults = {
        "id": _next_id() + 100_000,
        "username": None,
        "first_name": "Test",
        "last_name": "User",
    }
    defaults.update(overrides)
    user = User(**defaults)
    session.add(user)
    await session.flush()
    return user


async def create_chat(session: AsyncSession, **overrides) -> Chat:
    defaults = {
        "id": -(_next_id() + 1_000_000_000_000),
        "title": "Test Chat",
        "type": "supergroup",
        "is_active": True,
    }
    defaults.update(overrides)
    chat = Chat(**defaults)
    session.add(chat)
    await session.flush()
    return chat


async def create_trigger(session: AsyncSession, chat_id: int, user_id: int | None = None, **overrides) -> Trigger:
    defaults = {
        "chat_id": chat_id,
        "key_phrase": f"test_key_{_next_id()}",
        "content": {"text": "Hello!"},
        "match_type": MatchType.EXACT,
        "is_case_sensitive": False,
        "access_level": AccessLevel.ALL,
        "created_by": user_id,
        "moderation_status": ModerationStatus.SAFE,
    }
    defaults.update(overrides)
    trigger = Trigger(**defaults)
    session.add(trigger)
    await session.flush()
    return trigger


async def create_warn(
    session: AsyncSession, chat_id: int, user_id: int, admin_id: int | None = None, **overrides
) -> Warn:
    defaults = {
        "chat_id": chat_id,
        "user_id": user_id,
        "admin_id": admin_id,
        "reason": "Test warn",
    }
    defaults.update(overrides)
    warn = Warn(**defaults)
    session.add(warn)
    await session.flush()
    return warn


async def create_banned_chat(session: AsyncSession, chat_id: int, **overrides) -> BannedChat:
    defaults = {
        "chat_id": chat_id,
        "reason": "Test ban",
    }
    defaults.update(overrides)
    banned = BannedChat(**defaults)
    session.add(banned)
    await session.flush()
    return banned
