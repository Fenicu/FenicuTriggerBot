import json
import re
from datetime import date

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.broker import broker
from app.core.valkey import valkey
from app.db.models.daily_stat import DailyStat
from app.db.models.trigger import AccessLevel, MatchType, ModerationStatus, Trigger
from app.schemas.moderation import TriggerModerationTask

CACHE_TTL = 3600


async def create_trigger(
    session: AsyncSession,
    chat_id: int,
    key_phrase: str,
    content: dict,
    match_type: MatchType = MatchType.EXACT,
    is_case_sensitive: bool = False,
    access_level: AccessLevel = AccessLevel.ALL,
    created_by: int = 0,
    skip_moderation: bool = False,
) -> Trigger:
    """Создать новый триггер."""
    moderation_status = ModerationStatus.SAFE if skip_moderation else ModerationStatus.PENDING

    trigger = Trigger(
        chat_id=chat_id,
        key_phrase=key_phrase,
        content=content,
        match_type=match_type,
        is_case_sensitive=is_case_sensitive,
        access_level=access_level,
        created_by=created_by,
        moderation_status=moderation_status,
    )
    session.add(trigger)
    await session.commit()
    await session.refresh(trigger)

    await valkey.delete(f"triggers:{chat_id}")

    if skip_moderation:
        return trigger

    # Prepare moderation task
    text_content = content.get("text")
    caption = content.get("caption")
    file_id = None
    file_type = None

    if content.get("photo"):
        file_type = "photo"
        # Get the largest photo
        file_id = content["photo"][-1]["file_id"]
    elif content.get("video"):
        file_type = "video"
        file_id = content["video"]["file_id"]
    elif content.get("animation"):
        file_type = "animation"
        file_id = content["animation"]["file_id"]
    elif content.get("document"):
        file_type = "document"
        file_id = content["document"]["file_id"]

    task = TriggerModerationTask(
        trigger_id=trigger.id,
        chat_id=chat_id,
        user_id=created_by,
        text_content=text_content,
        caption=caption,
        file_id=file_id,
        file_type=file_type,
    )

    await broker.publish(task, "q.moderation.analyze")

    return trigger


async def get_triggers_by_chat(session: AsyncSession, chat_id: int) -> list[Trigger]:
    """Получить все триггеры чата (с кэшированием)."""
    cache_key = f"triggers:{chat_id}"
    cached_data = await valkey.get(cache_key)

    if cached_data:
        triggers_data = json.loads(cached_data)
        triggers = []
        for t_data in triggers_data:
            t_data["match_type"] = MatchType(t_data["match_type"])
            t_data["access_level"] = AccessLevel(t_data["access_level"])
            t = Trigger(**t_data)
            triggers.append(t)
        return triggers

    stmt = select(Trigger).where(Trigger.chat_id == chat_id)
    result = await session.execute(stmt)
    triggers = result.scalars().all()

    triggers_list = []
    for t in triggers:
        t_dict = {
            "id": t.id,
            "chat_id": t.chat_id,
            "key_phrase": t.key_phrase,
            "content": t.content,
            "match_type": t.match_type.value,
            "is_case_sensitive": t.is_case_sensitive,
            "access_level": t.access_level.value,
            "usage_count": t.usage_count,
            "created_by": t.created_by,
        }
        triggers_list.append(t_dict)

    await valkey.set(cache_key, json.dumps(triggers_list), ex=CACHE_TTL)

    return list(triggers)


async def find_matches(triggers: list[Trigger], text: str) -> list[Trigger]:
    """Найти все подходящие триггеры для текста."""
    matches = []
    regex_triggers = [t for t in triggers if t.match_type == MatchType.REGEXP]
    exact_triggers = [t for t in triggers if t.match_type == MatchType.EXACT]
    contains_triggers = [t for t in triggers if t.match_type == MatchType.CONTAINS]

    for t in regex_triggers:
        flags = 0 if t.is_case_sensitive else re.IGNORECASE
        try:
            if re.search(t.key_phrase, text, flags):
                matches.append(t)
        except re.error:
            continue

    for t in exact_triggers:
        if t.is_case_sensitive:
            if text == t.key_phrase:
                matches.append(t)
        else:
            if text.lower() == t.key_phrase.lower():
                matches.append(t)

    for t in contains_triggers:
        if t.is_case_sensitive:
            if t.key_phrase in text:
                matches.append(t)
        else:
            if t.key_phrase.lower() in text.lower():
                matches.append(t)

    return matches


async def get_trigger_by_key(session: AsyncSession, chat_id: int, key_phrase: str) -> Trigger | None:
    """Получить триггер по ключу."""
    stmt = select(Trigger).where(Trigger.chat_id == chat_id, Trigger.key_phrase == key_phrase)
    result = await session.execute(stmt)
    return result.scalars().first()


async def delete_trigger_by_key(session: AsyncSession, chat_id: int, key_phrase: str) -> bool:
    """Удалить триггер по ключу."""
    stmt = select(Trigger).where(Trigger.chat_id == chat_id, Trigger.key_phrase == key_phrase)
    result = await session.execute(stmt)
    trigger = result.scalars().first()

    if trigger:
        await session.delete(trigger)
        await session.commit()
        await valkey.delete(f"triggers:{chat_id}")
        return True
    return False


async def increment_usage(session: AsyncSession, trigger_id: int) -> None:
    """Увеличить счетчик использования триггера."""
    stmt = update(Trigger).where(Trigger.id == trigger_id).values(usage_count=Trigger.usage_count + 1)
    await session.execute(stmt)

    today = date.today()
    stat_stmt = (
        insert(DailyStat)
        .values(date=today, triggers_count=1)
        .on_conflict_do_update(
            index_elements=[DailyStat.date],
            set_={DailyStat.triggers_count: DailyStat.triggers_count + 1},
        )
    )
    await session.execute(stat_stmt)

    await session.commit()


async def get_triggers_count(session: AsyncSession, chat_id: int) -> int:
    """Получить количество триггеров в чате."""
    stmt = select(func.count()).select_from(Trigger).where(Trigger.chat_id == chat_id)
    return (await session.execute(stmt)).scalar() or 0


async def get_triggers_paginated(
    session: AsyncSession, chat_id: int, page: int, page_size: int
) -> tuple[list[Trigger], int]:
    """Получить список триггеров с пагинацией."""
    offset = (page - 1) * page_size

    total = await get_triggers_count(session, chat_id)

    stmt = select(Trigger).where(Trigger.chat_id == chat_id).order_by(Trigger.id).offset(offset).limit(page_size)
    result = await session.execute(stmt)
    triggers = result.scalars().all()

    return list(triggers), total


async def get_trigger_by_id(session: AsyncSession, trigger_id: int) -> Trigger | None:
    """Получить триггер по ID."""
    return await session.get(Trigger, trigger_id)


async def update_trigger(session: AsyncSession, trigger_id: int, **kwargs) -> Trigger | None:
    """Обновить триггер."""
    trigger = await get_trigger_by_id(session, trigger_id)
    if not trigger:
        return None

    for key, value in kwargs.items():
        setattr(trigger, key, value)

    await session.commit()
    await session.refresh(trigger)

    await valkey.delete(f"triggers:{trigger.chat_id}")

    return trigger


async def delete_trigger_by_id(session: AsyncSession, trigger_id: int) -> bool:
    """Удалить триггер по ID."""
    trigger = await get_trigger_by_id(session, trigger_id)
    if not trigger:
        return False

    chat_id = trigger.chat_id
    await session.delete(trigger)
    await session.commit()

    await valkey.delete(f"triggers:{chat_id}")

    return True


async def delete_all_triggers_by_chat(session: AsyncSession, chat_id: int) -> int:
    """Удалить все триггеры чата."""
    stmt = delete(Trigger).where(Trigger.chat_id == chat_id)
    result = await session.execute(stmt)
    deleted_count = result.rowcount
    await session.commit()

    await valkey.delete(f"triggers:{chat_id}")

    return deleted_count
