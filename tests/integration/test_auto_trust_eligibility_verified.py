from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.db.models.trigger import ModerationStatus
from app.services import chat_trust_service
from tests.factories import create_chat, create_trigger, create_user


async def seed_safe_results(session, chat_id, *, authors=3, count=20, hours=24, deleted=0, category="Safe"):
    users = [await create_user(session) for _ in range(authors)]
    now = datetime.now(UTC)
    for i in range(count):
        await create_trigger(
            session,
            chat_id,
            user_id=users[i % authors].id if users else None,
            moderation_status=ModerationStatus.SAFE,
            moderation_category=category,
            created_at=now - timedelta(hours=hours * i / (count - 1)),
            is_deleted=i < deleted,
        )


@pytest.mark.parametrize(
    "options,expected",
    [
        ({"authors": 1, "hours": 48}, False),
        ({"authors": 2, "hours": 48}, False),
        ({"authors": 0, "hours": 48}, False),
        ({"hours": 23.99}, False),
        ({"deleted": 1}, False),
        ({"category": None}, False),
        ({"category": "Scam"}, False),
        ({"hours": 24}, True),
        ({"hours": 48}, True),
    ],
)
async def test_streak_grant_requires_live_diverse_safe_results_over_a_day(db_session, options, expected):
    chat = await create_chat(db_session, moderation_safe_streak=settings.TRUST_AUTO_STREAK_THRESHOLD - 1)
    await seed_safe_results(db_session, chat.id, **options)
    await db_session.commit()
    with patch.object(chat_trust_service, "_notify_trust_change", AsyncMock()) as notify:
        changed = await chat_trust_service.register_moderation_outcome(db_session, chat.id, flagged=False)
    await db_session.refresh(chat)
    assert changed is expected
    assert chat.is_trusted is expected
    assert notify.await_count == int(expected)


async def test_streak_counter_without_safe_rows_does_not_grant_trust(db_session):
    chat = await create_chat(db_session, moderation_safe_streak=settings.TRUST_AUTO_STREAK_THRESHOLD - 1)
    await db_session.commit()
    with patch.object(chat_trust_service, "_notify_trust_change", AsyncMock()):
        assert await chat_trust_service.register_moderation_outcome(db_session, chat.id, flagged=False) is False


async def test_deleted_results_cannot_supply_authors_or_age(db_session):
    chat = await create_chat(db_session, moderation_safe_streak=20)
    await seed_safe_results(db_session, chat.id, authors=2, count=20, hours=1)
    third_author = await create_user(db_session)
    await create_trigger(
        db_session,
        chat.id,
        user_id=third_author.id,
        moderation_category="Safe",
        is_deleted=True,
        created_at=datetime.now(UTC) - timedelta(days=2),
    )
    await db_session.commit()
    with patch.object(chat_trust_service, "_notify_trust_change", AsyncMock()):
        assert await chat_trust_service.register_moderation_outcome(db_session, chat.id, flagged=False) is False


async def test_old_safe_rows_do_not_supply_evidence_for_a_new_streak(db_session):
    chat = await create_chat(db_session, moderation_safe_streak=19)
    for _ in range(3):
        user = await create_user(db_session)
        await create_trigger(
            db_session,
            chat.id,
            user_id=user.id,
            moderation_category="Safe",
            created_at=datetime.now(UTC) - timedelta(days=2),
        )
    await seed_safe_results(db_session, chat.id, authors=1, count=20, hours=1)
    await db_session.commit()
    with patch.object(chat_trust_service, "_notify_trust_change", AsyncMock()):
        assert await chat_trust_service.register_moderation_outcome(db_session, chat.id, flagged=False) is False
