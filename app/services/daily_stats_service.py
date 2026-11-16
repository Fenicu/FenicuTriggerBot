import asyncio
import contextlib
import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import date

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.valkey import valkey
from app.db.models.daily_stat import DailyStat

logger = logging.getLogger(__name__)

# Хэш несброшенных счётчиков: поле "<ISO-дата>:<колонка DailyStat>"
PENDING_KEY = "daily_stats:pending"
FLUSH_INTERVAL = 60
_FIELDS = ("messages_count", "triggers_count")


async def _count(field: str) -> None:
    try:
        await valkey.hincrby(PENDING_KEY, f"{date.today().isoformat()}:{field}", 1)
    except Exception as e:
        logger.warning("Failed to count %s: %s", field, e)


async def count_message() -> None:
    """Учесть входящее сообщение в суточной статистике."""
    await _count("messages_count")


async def count_trigger_usage() -> None:
    """Учесть срабатывание триггера в суточной статистике."""
    await _count("triggers_count")


async def flush_daily_stats(session_factory: Callable[[], AsyncSession] = async_session_factory) -> None:
    """Перенести накопленные счётчики из Valkey в DailyStat."""
    # MULTI/EXEC: забираем и удаляем атомарно, инкременты между ними не теряются
    async with valkey.pipeline(transaction=True) as pipe:
        pipe.hgetall(PENDING_KEY)
        pipe.delete(PENDING_KEY)
        pending, _ = await pipe.execute()

    if not pending:
        return

    by_day: dict[date, dict[str, int]] = defaultdict(dict)
    for raw_field, raw_value in pending.items():
        day, _, field = raw_field.partition(":")
        if field not in _FIELDS:
            logger.warning("Unknown daily stat counter %s, dropped", raw_field)
            continue
        by_day[date.fromisoformat(day)][field] = int(raw_value)

    try:
        async with session_factory() as session:
            for day, counts in sorted(by_day.items()):
                stmt = (
                    insert(DailyStat)
                    .values(date=day, **counts)
                    .on_conflict_do_update(
                        index_elements=[DailyStat.date],
                        set_={field: getattr(DailyStat, field) + value for field, value in counts.items()},
                    )
                )
                await session.execute(stmt)
            await session.commit()
    except BaseException:
        # БД недоступна или запись отменили на shutdown -- возвращаем счётчики,
        # следующий сброс их подберёт. CancelledError тоже не должен терять батч.
        for raw_field, raw_value in pending.items():
            await valkey.hincrby(PENDING_KEY, raw_field, int(raw_value))
        raise


async def run_flush_loop(interval: float = FLUSH_INTERVAL, stop_event: asyncio.Event | None = None) -> None:
    """Фоновая задача: периодический сброс счётчиков в БД.

    Останавливается установкой stop_event, а не отменой: отмена могла прийти
    между HGETALL+DEL и записью в БД и потерять уже забранный батч.
    """
    stop_event = stop_event or asyncio.Event()
    while not stop_event.is_set():
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        if stop_event.is_set():
            break
        try:
            await flush_daily_stats()
        except Exception:
            logger.exception("Failed to flush daily stats")
