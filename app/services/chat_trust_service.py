"""Автоматическая выдача/снятие доверия чату по репутации модерации.

Chat.is_trusted (когда выдан) освобождает создание триггеров в чате от вызова
LLM-модерации (см. app/bot/handlers/creation.py). Этот сервис ведёт два
счётчика на стороне БД — стрик чистых исходов модерации и число ложных
позитивов — и по достижении порога выдаёт доверие автоматически, помечая его
как trust_auto_granted, чтобы отличать от доверия, выданного человеком.
"""

import html
import logging

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.instance import bot
from app.core.config import settings
from app.db.models.chat import Chat
from app.db.models.trust_history import ChatTrustHistory

logger = logging.getLogger(__name__)


async def register_moderation_outcome(
    session: AsyncSession,
    chat_id: int,
    *,
    flagged: bool,
    silent: bool = False,
) -> bool:
    """Учитывает исход модерации триггера в репутации чата.

    silent=True — тихая bulk-перемодерация старых триггеров, она не должна
    накручивать стрик и не может выдать доверие.
    flagged=True обнуляет стрик независимо от silent и, если чат доверен
    автоматически, снимает доверие.
    Коммитит сессию сама. Возвращает True, если статус доверия чата изменился.
    """
    if not flagged and silent:
        return False

    if flagged:
        stmt = (
            update(Chat)
            .where(Chat.id == chat_id)
            .values(moderation_safe_streak=0)
            .returning(Chat.is_trusted, Chat.trust_auto_granted)
        )
    else:
        stmt = (
            update(Chat)
            .where(Chat.id == chat_id)
            .values(moderation_safe_streak=Chat.moderation_safe_streak + 1)
            .returning(Chat.moderation_safe_streak, Chat.is_trusted)
        )

    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        await session.commit()
        return False

    changed = False
    if flagged:
        is_trusted, trust_auto_granted = row
        if settings.TRUST_AUTO_ENABLED and is_trusted and trust_auto_granted:
            changed = await _revoke_trust(session, chat_id)
    else:
        safe_streak, is_trusted = row
        if settings.TRUST_AUTO_ENABLED and not is_trusted and safe_streak >= settings.TRUST_AUTO_STREAK_THRESHOLD:
            changed = await _grant_trust(
                session, chat_id, reason=f"накоплен стрик из {safe_streak} чистых проверок подряд"
            )

    await session.commit()
    return changed


async def register_false_positive(session: AsyncSession, chat_id: int) -> bool:
    """Учитывает ложное срабатывание модерации триггера в репутации чата.

    Коммитит сессию сама. Возвращает True, если чату выдано доверие.
    """
    stmt = (
        update(Chat)
        .where(Chat.id == chat_id)
        .values(moderation_false_positive_count=Chat.moderation_false_positive_count + 1)
        .returning(Chat.moderation_false_positive_count, Chat.is_trusted)
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        await session.commit()
        return False

    false_positive_count, is_trusted = row
    changed = False
    if (
        settings.TRUST_AUTO_ENABLED
        and not is_trusted
        and false_positive_count >= settings.TRUST_AUTO_FALSE_POSITIVE_THRESHOLD
    ):
        changed = await _grant_trust(
            session,
            chat_id,
            reason=f"накоплено {false_positive_count} ложных срабатываний, снятых модератором",
        )

    await session.commit()
    return changed


async def revoke_auto_trust(session: AsyncSession, chat_id: int) -> bool:
    """Снимает автоматически выданное доверие чата напрямую.

    Доверие, выданное человеком (trust_auto_granted=False), не трогает.
    Коммитит сессию сама. Возвращает True, если доверие было снято.
    """
    changed = await _revoke_trust(session, chat_id)
    await session.commit()
    return changed


async def _grant_trust(session: AsyncSession, chat_id: int, *, reason: str) -> bool:
    """Атомарно выдаёт автоматическое доверие чату, если оно ещё не выдано."""
    stmt = (
        update(Chat)
        .where(Chat.id == chat_id, Chat.is_trusted.is_(False))
        .values(is_trusted=True, trust_auto_granted=True)
        .returning(Chat.id, Chat.title)
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        return False

    _, title = row
    session.add(ChatTrustHistory(chat_id=chat_id, user_id=None, event_type="granted_auto"))
    logger.info("chat %s granted auto trust", chat_id)
    await _notify_trust_change(chat_id, title, granted=True, reason=reason)
    return True


async def _revoke_trust(session: AsyncSession, chat_id: int) -> bool:
    """Атомарно снимает автоматическое доверие чата (не трогает выданное вручную)."""
    stmt = (
        update(Chat)
        .where(Chat.id == chat_id, Chat.is_trusted.is_(True), Chat.trust_auto_granted.is_(True))
        .values(is_trusted=False, trust_auto_granted=False, moderation_safe_streak=0)
        .returning(Chat.id, Chat.title)
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        return False

    _, title = row
    session.add(ChatTrustHistory(chat_id=chat_id, user_id=None, event_type="revoked_auto"))
    logger.info("chat %s auto trust revoked", chat_id)
    await _notify_trust_change(chat_id, title, granted=False, reason="сработал флаг модерации")
    return True


async def _notify_trust_change(chat_id: int, chat_title: str | None, *, granted: bool, reason: str) -> None:
    """Уведомляет канал модерации о выдаче/снятии авто-доверия чату.

    Сбой отправки (сеть, бан бота в канале и т.п.) не должен ронять учёт репутации
    модерации — исключение гасится здесь же, доверие остаётся выданным/снятым.
    """
    title_html = html.escape(chat_title) if chat_title else "—"
    if granted:
        header = "Чату выдано авто-доверие"
        meaning = "LLM больше не проверяет новые триггеры этого чата."
    else:
        header = "Авто-доверие снято"
        meaning = "Проверка LLM возобновлена."

    text = f"<b>{header}</b>\nЧат: {title_html} (<code>{chat_id}</code>)\nПричина: {reason}\n{meaning}"

    try:
        await bot.send_message(settings.MODERATION_CHANNEL_ID, text, parse_mode="HTML")
    except Exception as e:
        logger.warning("Failed to notify moderation channel about trust change for chat %s: %s", chat_id, e)
