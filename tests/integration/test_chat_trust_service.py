"""Integration tests for app/services/chat_trust_service.py."""

from app.core.config import settings
from app.db.models.trust_history import ChatTrustHistory
from app.services import chat_trust_service
from sqlalchemy import select

from tests.factories import create_chat


async def _history_events(session, chat_id: int) -> list[str]:
    stmt = select(ChatTrustHistory.event_type).where(ChatTrustHistory.chat_id == chat_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ── register_moderation_outcome: чистый исход ────────────────────────────────


async def test_register_moderation_outcome_increments_streak_on_clean_outcome(db_session):
    """Каждый чистый (не flagged, не silent) исход увеличивает стрик на единицу."""
    chat = await create_chat(db_session)
    await db_session.commit()

    for _ in range(3):
        changed = await chat_trust_service.register_moderation_outcome(db_session, chat.id, flagged=False)
        assert changed is False

    await db_session.refresh(chat)
    assert chat.moderation_safe_streak == 3
    assert chat.is_trusted is False


async def test_register_moderation_outcome_grants_trust_at_threshold(db_session):
    """По достижении порога стрика чату выдаётся автоматическое доверие с записью в историю."""
    chat = await create_chat(db_session, moderation_safe_streak=settings.TRUST_AUTO_STREAK_THRESHOLD - 1)
    await db_session.commit()

    changed = await chat_trust_service.register_moderation_outcome(db_session, chat.id, flagged=False)
    assert changed is True

    await db_session.refresh(chat)
    assert chat.moderation_safe_streak == settings.TRUST_AUTO_STREAK_THRESHOLD
    assert chat.is_trusted is True
    assert chat.trust_auto_granted is True

    events = await _history_events(db_session, chat.id)
    assert events == ["granted_auto"]


async def test_register_moderation_outcome_already_trusted_not_regranted(db_session):
    """Если чат уже доверенный, повторное достижение порога ничего не меняет."""
    chat = await create_chat(
        db_session,
        is_trusted=True,
        trust_auto_granted=True,
        moderation_safe_streak=settings.TRUST_AUTO_STREAK_THRESHOLD,
    )
    await db_session.commit()

    changed = await chat_trust_service.register_moderation_outcome(db_session, chat.id, flagged=False)
    assert changed is False

    events = await _history_events(db_session, chat.id)
    assert events == []


# ── register_moderation_outcome: silent ──────────────────────────────────────


async def test_register_moderation_outcome_silent_does_not_increment_streak(db_session):
    """silent=True (bulk-перемодерация) не должен накручивать стрик и не выдаёт доверие."""
    chat = await create_chat(db_session, moderation_safe_streak=5)
    await db_session.commit()

    changed = await chat_trust_service.register_moderation_outcome(db_session, chat.id, flagged=False, silent=True)
    assert changed is False

    await db_session.refresh(chat)
    assert chat.moderation_safe_streak == 5
    assert chat.is_trusted is False


# ── register_moderation_outcome: flagged ─────────────────────────────────────


async def test_register_moderation_outcome_flagged_resets_streak(db_session):
    """flagged=True обнуляет стрик независимо от текущего значения."""
    chat = await create_chat(db_session, moderation_safe_streak=15)
    await db_session.commit()

    changed = await chat_trust_service.register_moderation_outcome(db_session, chat.id, flagged=True)
    assert changed is False

    await db_session.refresh(chat)
    assert chat.moderation_safe_streak == 0


async def test_register_moderation_outcome_flagged_silent_also_resets_streak(db_session):
    """flagged=True обнуляет стрик даже при silent=True."""
    chat = await create_chat(db_session, moderation_safe_streak=15)
    await db_session.commit()

    await chat_trust_service.register_moderation_outcome(db_session, chat.id, flagged=True, silent=True)

    await db_session.refresh(chat)
    assert chat.moderation_safe_streak == 0


async def test_register_moderation_outcome_flagged_revokes_auto_trust(db_session):
    """flagged=True снимает автоматически выданное доверие и пишет revoked_auto в историю."""
    chat = await create_chat(
        db_session,
        is_trusted=True,
        trust_auto_granted=True,
        moderation_safe_streak=15,
    )
    await db_session.commit()

    changed = await chat_trust_service.register_moderation_outcome(db_session, chat.id, flagged=True)
    assert changed is True

    await db_session.refresh(chat)
    assert chat.is_trusted is False
    assert chat.trust_auto_granted is False
    assert chat.moderation_safe_streak == 0

    events = await _history_events(db_session, chat.id)
    assert events == ["revoked_auto"]


async def test_register_moderation_outcome_flagged_does_not_revoke_manual_trust(db_session):
    """Доверие, выданное человеком (trust_auto_granted=False), автоматика никогда не снимает."""
    chat = await create_chat(db_session, is_trusted=True, trust_auto_granted=False)
    await db_session.commit()

    changed = await chat_trust_service.register_moderation_outcome(db_session, chat.id, flagged=True)
    assert changed is False

    await db_session.refresh(chat)
    assert chat.is_trusted is True
    assert chat.trust_auto_granted is False

    events = await _history_events(db_session, chat.id)
    assert events == []


# ── register_false_positive ──────────────────────────────────────────────────


async def test_register_false_positive_increments_counter(db_session):
    """Каждый ложный позитив увеличивает счётчик."""
    chat = await create_chat(db_session)
    await db_session.commit()

    changed = await chat_trust_service.register_false_positive(db_session, chat.id)
    assert changed is False

    await db_session.refresh(chat)
    assert chat.moderation_false_positive_count == 1


async def test_register_false_positive_grants_trust_at_threshold(db_session):
    """Три ложных позитива выдают автоматическое доверие."""
    chat = await create_chat(
        db_session,
        moderation_false_positive_count=settings.TRUST_AUTO_FALSE_POSITIVE_THRESHOLD - 1,
    )
    await db_session.commit()

    changed = await chat_trust_service.register_false_positive(db_session, chat.id)
    assert changed is True

    await db_session.refresh(chat)
    assert chat.moderation_false_positive_count == settings.TRUST_AUTO_FALSE_POSITIVE_THRESHOLD
    assert chat.is_trusted is True
    assert chat.trust_auto_granted is True

    events = await _history_events(db_session, chat.id)
    assert events == ["granted_auto"]


# ── revoke_auto_trust ─────────────────────────────────────────────────────────


async def test_revoke_auto_trust_revokes_and_records_history(db_session):
    """revoke_auto_trust снимает автоматическое доверие и пишет revoked_auto в историю."""
    chat = await create_chat(db_session, is_trusted=True, trust_auto_granted=True)
    await db_session.commit()

    changed = await chat_trust_service.revoke_auto_trust(db_session, chat.id)
    assert changed is True

    await db_session.refresh(chat)
    assert chat.is_trusted is False
    assert chat.trust_auto_granted is False

    events = await _history_events(db_session, chat.id)
    assert events == ["revoked_auto"]


async def test_revoke_auto_trust_ignores_manual_trust(db_session):
    """revoke_auto_trust не трогает доверие, выданное вручную."""
    chat = await create_chat(db_session, is_trusted=True, trust_auto_granted=False)
    await db_session.commit()

    changed = await chat_trust_service.revoke_auto_trust(db_session, chat.id)
    assert changed is False

    await db_session.refresh(chat)
    assert chat.is_trusted is True


# ── settings.TRUST_AUTO_ENABLED ──────────────────────────────────────────────


async def test_trust_auto_disabled_streak_grows_but_no_grant(db_session, monkeypatch):
    """При выключенном TRUST_AUTO_ENABLED счётчик растёт, но доверие не выдаётся."""
    monkeypatch.setattr(settings, "TRUST_AUTO_ENABLED", False)

    chat = await create_chat(db_session, moderation_safe_streak=settings.TRUST_AUTO_STREAK_THRESHOLD - 1)
    await db_session.commit()

    changed = await chat_trust_service.register_moderation_outcome(db_session, chat.id, flagged=False)
    assert changed is False

    await db_session.refresh(chat)
    assert chat.moderation_safe_streak == settings.TRUST_AUTO_STREAK_THRESHOLD
    assert chat.is_trusted is False

    events = await _history_events(db_session, chat.id)
    assert events == []


async def test_trust_auto_disabled_does_not_revoke_on_flagged(db_session, monkeypatch):
    """При выключенном TRUST_AUTO_ENABLED автоматическое доверие не снимается по flagged."""
    monkeypatch.setattr(settings, "TRUST_AUTO_ENABLED", False)

    chat = await create_chat(db_session, is_trusted=True, trust_auto_granted=True, moderation_safe_streak=10)
    await db_session.commit()

    changed = await chat_trust_service.register_moderation_outcome(db_session, chat.id, flagged=True)
    assert changed is False

    await db_session.refresh(chat)
    assert chat.is_trusted is True
    assert chat.trust_auto_granted is True
    assert chat.moderation_safe_streak == 0  # стрик всё равно обнуляется


async def test_trust_auto_disabled_false_positive_counter_grows_no_grant(db_session, monkeypatch):
    """При выключенном TRUST_AUTO_ENABLED счётчик ложных позитивов растёт, но доверие не выдаётся."""
    monkeypatch.setattr(settings, "TRUST_AUTO_ENABLED", False)

    chat = await create_chat(
        db_session,
        moderation_false_positive_count=settings.TRUST_AUTO_FALSE_POSITIVE_THRESHOLD - 1,
    )
    await db_session.commit()

    changed = await chat_trust_service.register_false_positive(db_session, chat.id)
    assert changed is False

    await db_session.refresh(chat)
    assert chat.moderation_false_positive_count == settings.TRUST_AUTO_FALSE_POSITIVE_THRESHOLD
    assert chat.is_trusted is False


# ── несуществующий чат ────────────────────────────────────────────────────────


async def test_register_moderation_outcome_nonexistent_chat_returns_false(db_session):
    """Несуществующий чат не роняет вызов и просто возвращает False."""
    changed = await chat_trust_service.register_moderation_outcome(db_session, -999999999, flagged=False)
    assert changed is False


async def test_register_moderation_outcome_flagged_nonexistent_chat_returns_false(db_session):
    """Несуществующий чат не роняет вызов и с flagged=True."""
    changed = await chat_trust_service.register_moderation_outcome(db_session, -999999998, flagged=True)
    assert changed is False


async def test_register_false_positive_nonexistent_chat_returns_false(db_session):
    """register_false_positive для несуществующего чата не роняет вызов."""
    changed = await chat_trust_service.register_false_positive(db_session, -999999997)
    assert changed is False


async def test_revoke_auto_trust_nonexistent_chat_returns_false(db_session):
    """revoke_auto_trust для несуществующего чата не роняет вызов."""
    changed = await chat_trust_service.revoke_auto_trust(db_session, -999999996)
    assert changed is False
