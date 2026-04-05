from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Chat
from app.db.models.reputation_log import ReputationLog
from app.db.models.user_chat import UserChat

DEFAULT_THRESHOLDS = [50, 200, 500, 1500, 5000]

PRESETS = {
    "neutral": {
        "ru": {0: "", 1: "Участник", 2: "Активный", 3: "Опытный", 4: "Эксперт", 5: "Легенда"},
        "en": {0: "", 1: "Member", 2: "Active", 3: "Skilled", 4: "Expert", 5: "Legend"},
    },
    "gaming": {
        "ru": {0: "", 1: "Бронза", 2: "Серебро", 3: "Золото", 4: "Платина", 5: "Алмаз"},
        "en": {0: "", 1: "Bronze", 2: "Silver", 3: "Gold", 4: "Platinum", 5: "Diamond"},
    },
    "numeric": {0: "", 1: "Lv.1", 2: "Lv.2", 3: "Lv.3", 4: "Lv.4", 5: "Lv.5"},
}


def get_thresholds(chat: Chat) -> list[int]:
    """Получить пороги уровней для чата."""
    if chat.tags_thresholds and isinstance(chat.tags_thresholds, list) and len(chat.tags_thresholds) == 5:
        return chat.tags_thresholds
    return DEFAULT_THRESHOLDS


def calculate_level(score: int, thresholds: list[int]) -> int:
    """Определить уровень по очкам."""
    for i, threshold in enumerate(thresholds):
        if score < threshold:
            return i
    return len(thresholds)


def get_level_name(level: int, chat: Chat) -> str:
    """Получить название уровня."""
    if chat.tags_custom and isinstance(chat.tags_custom, dict):
        return chat.tags_custom.get(str(level), "")
    preset = PRESETS.get(chat.tags_preset, PRESETS["neutral"])
    if isinstance(preset, dict) and "ru" in preset:
        # Localized preset
        lang = chat.language_code if chat.language_code in preset else "ru"
        return preset[lang].get(level, "")
    # Non-localized preset (numeric)
    return preset.get(level, "")


async def add_message_score(
    session: AsyncSession,
    user_chat: UserChat,
    chat: Chat,
) -> int | None:
    """Начислить очки за сообщение. Возвращает новый уровень если изменился, иначе None."""
    today = date.today()

    # Антифлуд: сброс дневного счётчика
    if user_chat.daily_message_date != today:
        user_chat.daily_message_date = today
        user_chat.daily_message_count = 0

    if user_chat.daily_message_count >= chat.tags_daily_message_limit:
        return None

    user_chat.daily_message_count += 1
    user_chat.reputation_score += chat.tags_weight_messages

    return _check_level_change(user_chat, chat)


async def add_reaction_score(
    session: AsyncSession,
    chat: Chat,
    from_user_id: int,
    to_user_id: int,
    chat_id: int,
) -> int | None:
    """Начислить очки за реакцию. Возвращает новый уровень если изменился, иначе None."""
    if from_user_id == to_user_id:
        return None

    today = date.today()

    log = await _get_or_create_log(session, chat_id, from_user_id, to_user_id, "reaction", today)
    if log.count >= chat.tags_daily_reaction_limit:
        return None

    log.count += 1

    user_chat = await session.get(UserChat, (to_user_id, chat_id))
    if not user_chat:
        return None

    user_chat.reputation_score += chat.tags_weight_reactions

    return _check_level_change(user_chat, chat)


async def add_reply_score(
    session: AsyncSession,
    chat: Chat,
    from_user_id: int,
    to_user_id: int,
    chat_id: int,
) -> int | None:
    """Начислить очки за ответ на сообщение. Возвращает новый уровень если изменился, иначе None."""
    if from_user_id == to_user_id:
        return None

    today = date.today()

    log = await _get_or_create_log(session, chat_id, from_user_id, to_user_id, "reply", today)
    if log.count >= chat.tags_daily_reaction_limit:
        return None

    log.count += 1

    user_chat = await session.get(UserChat, (to_user_id, chat_id))
    if not user_chat:
        return None

    user_chat.reputation_score += chat.tags_weight_replies

    return _check_level_change(user_chat, chat)


def _check_level_change(user_chat: UserChat, chat: Chat) -> int | None:
    """Проверить, изменился ли уровень. Вернуть новый уровень или None."""
    thresholds = get_thresholds(chat)
    new_level = calculate_level(user_chat.reputation_score, thresholds)

    if new_level > user_chat.reputation_level:
        user_chat.reputation_level = new_level
        return new_level

    return None


async def _get_or_create_log(
    session: AsyncSession,
    chat_id: int,
    from_user_id: int,
    to_user_id: int,
    action_type: str,
    today: date,
) -> ReputationLog:
    """Получить или создать запись антифлуд-лога."""
    stmt = select(ReputationLog).where(
        ReputationLog.chat_id == chat_id,
        ReputationLog.from_user_id == from_user_id,
        ReputationLog.to_user_id == to_user_id,
        ReputationLog.action_type == action_type,
        ReputationLog.date == today,
    )
    result = await session.execute(stmt)
    log = result.scalar_one_or_none()

    if not log:
        log = ReputationLog(
            chat_id=chat_id,
            from_user_id=from_user_id,
            to_user_id=to_user_id,
            action_type=action_type,
            date=today,
            count=0,
        )
        session.add(log)
        await session.flush()

    return log


async def get_user_rank(session: AsyncSession, chat_id: int, user_id: int) -> int | None:
    """Получить позицию пользователя в рейтинге чата."""
    stmt = (
        select(UserChat.user_id)
        .where(UserChat.chat_id == chat_id, UserChat.is_active.is_(True))
        .order_by(UserChat.reputation_score.desc())
    )
    result = await session.execute(stmt)
    users = result.scalars().all()

    for i, uid in enumerate(users, 1):
        if uid == user_id:
            return i
    return None


async def get_active_users_count(session: AsyncSession, chat_id: int) -> int:
    """Получить количество активных пользователей в чате."""
    stmt = select(func.count()).where(UserChat.chat_id == chat_id, UserChat.is_active.is_(True))
    return await session.scalar(stmt) or 0
